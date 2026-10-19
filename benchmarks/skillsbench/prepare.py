"""Acquire/verify the pinned SkillsBench dataset; no containers or model calls."""
import argparse
import tomllib
from pathlib import Path

from pennybench.config import load_local_config
from pennybench.datasets import dataset_dir, ensure_dataset
from pennybench.digest import tree_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    suite = Path(__file__).resolve().parent
    root = suite.parents[1]
    source = tomllib.loads((suite / "source.toml").read_text())
    config = load_local_config(root / "pennybench.local.toml")
    store = config.store / ".datasets"
    if args.verify_only:
        tasks = dataset_dir(source["dataset"], store)
        if not tasks.is_dir():
            raise SystemExit(f"Pinned source is missing: {tasks}")
        actual = tree_sha256(tasks)
        if actual != source["task_tree_sha256"]:
            raise SystemExit(f"Task-tree hash mismatch: {actual}")
    else:
        tasks = ensure_dataset(source["dataset"], source["task_tree_sha256"], store)
    count = len(list(tasks.glob("*/task.toml")))
    if count != source["task_count"]:
        raise SystemExit(f"Task-count mismatch: {count}")
    print(f"Verified {source['dataset']}: {count} tasks; SHA256 {source['task_tree_sha256']}")


if __name__ == "__main__":
    main()
