"""Oracle pass: run each task's reference solution to find tasks broken on this machine.

A task whose own solution fails cannot measure an agent, so it becomes a pre-registered
exclusion before any model runs. No model is called.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from pennybench.config import LocalConfig
from pennybench.environment import (record_environment, remove_stray_containers,
                                    remove_stray_images)
from pennybench.harbor import harbor_bin, run_harbor
from pennybench.spec import Experiment

# SkillsBench reference solutions look for their task's skills at /skills, at ~/.claude/skills
# (where the tasks that copy skills in themselves put them), or at `skills/` relative to the
# image's working directory. Oracle runs as root.
ORACLE_SKILLS_PATHS = ("/skills", "/root/.claude/skills")


def image_workdir(task_dir: Path) -> str:
    """The last WORKDIR in the task's Dockerfile, which is where its solution runs."""
    workdir = "/"
    dockerfile = task_dir / "environment" / "Dockerfile"
    for line in dockerfile.read_text().splitlines() if dockerfile.exists() else []:
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].upper() == "WORKDIR":
            workdir = parts[1].strip().strip("\"'")
    return workdir

HOST_VARS = ("PATH", "HOME", "USER", "TMPDIR", "LANG")


def oracle_dir(experiment: Experiment, config: LocalConfig) -> Path:
    source = experiment.tasks_source
    key = source.get("dataset", source.get("path", "tasks")).replace("/", "__")
    return config.store / "oracle" / key


def run_oracle_task(task_dir: Path, out_dir: Path, config: LocalConfig) -> dict:
    env = {k: os.environ[k] for k in HOST_VARS if k in os.environ}
    if config.builder:
        env.update(config.builder.env())
    argv = [harbor_bin(), "run", "-p", str(task_dir), "-a", "oracle", "-o", str(out_dir / "harbor"),
            "-n", "1", "--no-delete"]
    skills = task_dir / "environment" / "skills"
    if skills.is_dir():
        targets = sorted({*ORACLE_SKILLS_PATHS, str(Path(image_workdir(task_dir)) / "skills")})
        argv += ["--mounts", json.dumps([{"type": "bind", "source": str(skills), "target": t,
                                          "read_only": True} for t in targets])]
    outcome = run_harbor(argv, env, out_dir / "harbor", out_dir / "harbor.log")
    result = outcome.result or {}
    environment = record_environment(result.get("trial_name"), out_dir)
    remove_stray_images(task_dir.name)
    remove_stray_containers(task_dir.name)
    record = {
        "task": task_dir.name,
        "status": outcome.status,
        "reward": (result.get("verifier_result") or {}).get("rewards", {}).get("reward"),
        "exception_type": (result.get("exception_info") or {}).get("exception_type"),
        "exception_message": ((result.get("exception_info") or {}).get("exception_message")
                              or "")[:500],
        "environment_sha256": environment["sha256"],
        "environment_error": environment["error"],
    }
    (out_dir / "oracle.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def run_oracle(experiment: Experiment, config: LocalConfig, workers: int = 2,
               retry_failed: bool = False, only: set[str] | None = None,
               on_result: Callable[[dict], None] = lambda r: None) -> list[dict]:
    """Every task in the experiment's set, minus its exclusions and ignoring any sample.
    Tasks with a saved result are not rerun, except where Harbor itself failed, or any
    failure when `retry_failed` is set."""
    if config.builder:
        config.builder.ensure()
    root = oracle_dir(experiment, config)
    excluded = {e.task for e in experiment.exclude}
    tasks = sorted(p.parent for p in experiment.tasks.glob("*/task.toml")
                   if p.parent.name not in excluded and (only is None or p.parent.name in only))
    results, pending = [], []
    for task in tasks:
        saved = root / task.name / "oracle.json"
        record = json.loads(saved.read_text()) if saved.exists() else None
        if record and record["status"] != "harbor_failed" and not (retry_failed and failed(record)):
            results.append(record)
        else:
            pending.append(task)
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {}
        for task in pending:
            out = root / task.name
            if (out / "harbor").exists():
                (out / "harbor").rename(out / f"harbor.previous-{len(list(out.glob('harbor.previous-*')))}")
            out.mkdir(parents=True, exist_ok=True)
            futures[pool.submit(run_oracle_task, task, out, config)] = task
        for future in as_completed(futures):
            record = future.result()
            if config.builder:
                record["cache_pruned"] = config.builder.enforce_cap()
            results.append(record)
            on_result(record)
    finally:
        # On Ctrl-C, queued tasks are dropped; tasks already running finish or are killed with
        # the process.
        pool.shutdown(wait=False, cancel_futures=True)
    results.sort(key=lambda r: r["task"])
    # The summary covers every saved verdict, so a filtered retry still leaves it complete.
    everything = sorted((json.loads(f.read_text()) for f in root.glob("*/oracle.json")),
                        key=lambda r: r["task"])
    (root / "summary.json").write_text(json.dumps(everything, indent=2) + "\n")
    return results


def failed(record: dict) -> bool:
    return record["status"] != "complete" or (record["reward"] or 0) < 1
