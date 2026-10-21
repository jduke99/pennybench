"""Acquire or verify the pinned tau3-bench task tree; makes no model calls.

The hub offers only `@latest`, so the pin is the content hash of the downloaded tree. A hash
mismatch means the hub's `latest` has moved since the pin was recorded.

Every task's Dockerfiles clone tau2-bench HEAD when they build, and the adapter's grader
calls the API as it was before tau2-bench v2.0.0 (2026-10-19), so unmodified tasks cannot be
graded. The pinned copy makes two edits in each Dockerfile; nothing else changes:
  1. fetch the commit in `source.toml` instead of HEAD;
  2. install `websockets>=13.0` (tau2's own constraint). At that commit `tau2.utils` imports
     it, but only the optional `voice` extra declares it, and the images install `knowledge`.
Experiments use the pinned copy.
"""

import argparse
import shutil
import subprocess
import tomllib
from pathlib import Path

from pennybench.digest import tree_sha256
from pennybench.harbor import harbor_bin


UPSTREAM_CLONE = 'git clone --depth=1 "${TAU2_BENCH_REPO}" "${TAU2_BENCH_ROOT}"'
UPSTREAM_INSTALL = '"${TAU2_BENCH_ROOT}[knowledge]"'
PINNED_INSTALL = UPSTREAM_INSTALL + ' "websockets>=13.0"'


def pinned_clone(commit: str) -> str:
    return ('mkdir -p "${TAU2_BENCH_ROOT}" && cd "${TAU2_BENCH_ROOT}" && git init -q '
            '&& git remote add origin "${TAU2_BENCH_REPO}" '
            f'&& git fetch -q --depth=1 origin {commit} && git checkout -q FETCH_HEAD && cd /')


def write_pinned(source: Path, target: Path, commit: str) -> int:
    """Copy `source` to `target`, applying the two Dockerfile edits in the module docstring."""
    staging = target.with_name(target.name + ".part")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(source, staging)
    edited = 0
    for dockerfile in staging.rglob("Dockerfile"):
        text = dockerfile.read_text()
        if text.count(UPSTREAM_CLONE) != 1 or text.count(UPSTREAM_INSTALL) != 1:
            raise SystemExit(f"{dockerfile}: expected exactly one tau2-bench clone and install")
        dockerfile.write_text(text.replace(UPSTREAM_CLONE, pinned_clone(commit))
                              .replace(UPSTREAM_INSTALL, PINNED_INSTALL))
        edited += 1
    staging.rename(target)
    return edited


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    suite = Path(__file__).resolve().parent
    root = suite.parents[1]
    source = tomllib.loads((suite / "source.toml").read_text())
    target = root / "runs/tau3-prep/source"
    if not target.exists():
        if args.verify_only:
            raise SystemExit(f"Pinned source is missing: {target}")
        staging = target.with_name("source.part")
        if staging.exists():
            raise SystemExit(f"Interrupted acquisition exists; inspect before retrying: {staging}")
        staging.mkdir(parents=True)
        subprocess.run([harbor_bin(), "download", source["dataset"], "-o", str(staging)], check=True)
        children = [p for p in staging.iterdir() if p.is_dir()]
        if len(children) != 1:
            raise SystemExit(f"Expected one dataset directory in {staging}, found {len(children)}")
        children[0].rename(target)
        shutil.rmtree(staging)
    actual = tree_sha256(target)
    if actual != source["task_tree_sha256"]:
        raise SystemExit(f"Task-tree hash mismatch: {actual}")
    tasks = sorted(p.parent.name for p in target.glob("*/task.toml"))
    if len(tasks) != source["task_count"]:
        raise SystemExit(f"Expected {source['task_count']} tasks, found {len(tasks)}")
    print(f"Verified tau3-bench: {len(tasks)} tasks; SHA256 {actual}")
    pinned = root / "runs/tau3-prep/pinned"
    if not pinned.exists():
        if args.verify_only:
            raise SystemExit(f"Pinned copy is missing: {pinned}")
        print(f"Edited {write_pinned(target, pinned, source['tau2_bench_commit'])} Dockerfiles")
    pinned_actual = tree_sha256(pinned)
    if pinned_actual != source["pinned_tree_sha256"]:
        raise SystemExit(f"Pinned-tree hash mismatch: {pinned_actual}")
    print(f"Verified pinned copy at tau2-bench {source['tau2_bench_commit'][:8]}; SHA256 {pinned_actual}")


if __name__ == "__main__":
    main()
