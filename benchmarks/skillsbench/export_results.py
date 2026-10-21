"""Export a sanitized, publishable summary of a finished SkillsBench run.

Reads a run directory and its report directory and writes derived data only: statistics,
per-trial metrics and outcomes, the audit and the sanitized manifest. Raw wire captures,
Harbor logs, transcripts and login metadata stay in the private run directory.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

TRIAL_FIELDS = (
    "pair", "position", "task", "rep", "role", "trial_id", "arm", "status", "reward",
    "exception_type", "agent_version", "task_checksum", "runner_wall_clock_s",
    "harbor_exit_code", "harbor_hung",
)
MANIFEST_DROP = {"host_home"}
PRIVATE = re.compile(r"/Users/[^/\s\"']+|/home/[^/\s\"']+|[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+|(?<![/\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?<!\d)(?!\w)|sk-ant-\S+|Bearer \S+")


def scrub(text: str) -> str:
    return PRIVATE.sub("<redacted>", text)


def export(run_dir: Path, report_dir: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in ("REPORT.md", "stats.json", "metrics.json", "audit.json"):
        (out / name).write_text(scrub((report_dir / name).read_text()))
    manifest = json.loads((report_dir / "run.json").read_text())
    for key in MANIFEST_DROP:
        manifest.pop(key, None)
    scope = manifest.get("analysis_scope")
    if isinstance(scope, dict):
        scope.pop("source_run", None)
    (out / "run.json").write_text(scrub(json.dumps(manifest, indent=2)) + "\n")
    skip = run_dir / "quantum-pair-skip.md"
    if skip.is_file():
        shutil.copyfile(skip, out / "operational-skip.md")
    trials = []
    reported = {row["trial_id"] for row in json.loads((report_dir / "metrics.json").read_text())}
    for path in sorted((run_dir / "trials").glob("*/trial.json")):
        if path.parent.name not in reported:
            continue
        trial = json.loads(path.read_text())
        trials.append({key: trial.get(key) for key in TRIAL_FIELDS})
    (out / "trials.json").write_text(json.dumps(trials, indent=1) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--report", type=Path, help="report directory; default <run>/partial-60-project-report")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = args.report or args.run_dir / "partial-60-project-report"
    export(args.run_dir, report, args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
