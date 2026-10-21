"""Acquire or verify the pinned MedAgentBench dataset; makes no model calls."""

import argparse
import subprocess
import tomllib
from pathlib import Path

from pennybench.digest import tree_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    suite = Path(__file__).resolve().parent
    root = suite.parents[1]
    source = tomllib.loads((suite / "source.toml").read_text())
    prep = root / "runs/medagentbench-prep"
    target = prep / "medagentbench"
    if not target.exists():
        if args.verify_only:
            raise SystemExit(f"Pinned source is missing: {target}")
        prep.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(root / ".venv/bin/harbor"), "download", source["registry_dataset"],
                        "-o", str(prep)], check=True)
    tasks = sorted(p for p in target.iterdir() if p.is_dir())
    if len(tasks) != source["task_count"]:
        raise SystemExit(f"Task count mismatch: {len(tasks)}")
    actual = tree_sha256(target)
    if actual != source["task_tree_sha256"]:
        raise SystemExit(f"Task-tree hash mismatch: {actual}")
    print(f"Verified MedAgentBench {source['registry_dataset']}: {len(tasks)} tasks; SHA256 {actual}")


if __name__ == "__main__":
    main()
