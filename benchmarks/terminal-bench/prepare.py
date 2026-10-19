"""Acquire or verify the pinned Terminal-Bench 2.1 source; makes no model calls."""

import argparse
import json
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
    target = root / "runs/terminal-bench-prep/source"
    if not target.exists():
        if args.verify_only:
            raise SystemExit(f"Pinned source is missing: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name("source.part")
        if staging.exists():
            raise SystemExit(f"Interrupted acquisition exists; inspect before retrying: {staging}")
        subprocess.run(["git", "init", str(staging)], check=True)
        subprocess.run(["git", "-C", str(staging), "remote", "add", "origin", source["repository"]], check=True)
        subprocess.run(["git", "-C", str(staging), "fetch", "--depth", "1", "origin", source["commit"]], check=True)
        subprocess.run(["git", "-C", str(staging), "checkout", "--detach", "FETCH_HEAD"], check=True)
        staging.rename(target)
    revision = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
    if revision != source["commit"]:
        raise SystemExit(f"Source revision mismatch: {revision}")
    tasks = target / source["tasks_subdirectory"]
    actual = tree_sha256(tasks)
    if actual != source["task_tree_sha256"]:
        raise SystemExit(f"Task-tree hash mismatch: {actual}")
    scope = json.loads((suite / "scope.json").read_text())
    rule = scope["selection_rule"]
    selected = []
    for path in sorted(tasks.glob("*/task.toml")):
        task = tomllib.loads(path.read_text())
        if (task["agent"]["timeout_sec"] <= rule["max_agent_timeout_sec"]
                and task["verifier"]["timeout_sec"] <= rule["max_verifier_timeout_sec"]
                and task["environment"]["memory_mb"] <= rule["max_task_memory_mb"]):
            selected.append(path.parent.name)
    if selected != scope["eligible_tasks_before_oracle_exclusions"]:
        raise SystemExit("Selected task list does not match the pinned selection rule")
    print(f"Verified Terminal-Bench 2.1 at {revision}: {len(selected)} selected tasks; SHA256 {actual}")


if __name__ == "__main__":
    main()
