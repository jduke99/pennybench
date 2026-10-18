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
from pennybench.harbor import harbor_bin, run_harbor
from pennybench.spec import Experiment

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
            "-n", "1"]
    outcome = run_harbor(argv, env, out_dir / "harbor", out_dir / "harbor.log")
    result = outcome.result or {}
    record = {
        "task": task_dir.name,
        "status": outcome.status,
        "reward": (result.get("verifier_result") or {}).get("rewards", {}).get("reward"),
        "exception_type": (result.get("exception_info") or {}).get("exception_type"),
        "exception_message": ((result.get("exception_info") or {}).get("exception_message")
                              or "")[:500],
    }
    (out_dir / "oracle.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def run_oracle(experiment: Experiment, config: LocalConfig, workers: int = 2,
               on_result: Callable[[dict], None] = lambda r: None) -> list[dict]:
    """Every task in the experiment's set, minus its exclusions and ignoring any sample.
    Tasks with a saved result are not rerun, except where Harbor itself failed."""
    if config.builder:
        config.builder.ensure()
    root = oracle_dir(experiment, config)
    excluded = {e.task for e in experiment.exclude}
    tasks = sorted(p.parent for p in experiment.tasks.glob("*/task.toml") if p.parent.name not in excluded)
    results, pending = [], []
    for task in tasks:
        saved = root / task.name / "oracle.json"
        record = json.loads(saved.read_text()) if saved.exists() else None
        if record and record["status"] != "harbor_failed":
            results.append(record)
        else:
            pending.append(task)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for task in pending:
            out = root / task.name
            out.mkdir(parents=True, exist_ok=True)
            futures[pool.submit(run_oracle_task, task, out, config)] = task
        for future in as_completed(futures):
            record = future.result()
            results.append(record)
            on_result(record)
            if config.builder:
                config.builder.enforce_cap()
    results.sort(key=lambda r: r["task"])
    (root / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    return results


def failed(record: dict) -> bool:
    return record["status"] != "complete" or (record["reward"] or 0) < 1
