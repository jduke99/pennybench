"""`pennybench` command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pennybench.agent_cache import AgentCacheError
from pennybench.agent_env import build_trial_env
from pennybench.datasets import DatasetError
from pennybench.audit import write_audit
from pennybench.report import build_report, format_report
from pennybench.config import LOCAL_CONFIG_NAME, ConfigError, load_local_config
from pennybench.plan import plan_trials
from pennybench.run import RunError, check_resumable, execute, start_run
from pennybench.builder import BuilderError
from pennybench.metrics import MetricsError
from pennybench.oracle import failed, oracle_dir, run_oracle
from pennybench.spec import SpecError, load_experiment
from pennybench.stats import StatsError


def read_dotenv(path: Path) -> dict[str, str]:
    """Secrets for the runner's own lookup. They are never exported to child processes
    except under the private names agent_env assigns."""
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _load(args):
    root = Path(args.root).resolve()
    config = load_local_config(root / LOCAL_CONFIG_NAME)
    experiment = load_experiment(Path(args.experiment).resolve(), root,
                                 dataset_store=config.store / ".datasets")
    environ = {**os.environ, **read_dotenv(root / ".env")}
    return root, config, experiment, environ


def cmd_check(args) -> int:
    _, config, experiment, environ = _load(args)
    trials = plan_trials(experiment)
    print(f"experiment  {experiment.id}  (stage {experiment.stage}, k={experiment.k})")
    print(f"variable    {experiment.variable}")
    for role, arm in (("baseline", experiment.baseline), ("treatment", experiment.treatment)):
        trial_env = build_trial_env(arm, config, environ)
        print(f"{role:<11} {arm.id}: {arm.route}, auth {arm.auth}, "
              f"agent env {sorted(trial_env.agent_env)}")
    tasks = experiment.task_dirs()
    print(f"tasks       {len(tasks)} ({len(experiment.exclude)} excluded), "
          f"{len(trials) // 2} pairs, {len(trials)} trials")
    return 0


def cmd_run(args) -> int:
    _, config, experiment, environ = _load(args)
    if args.resume:
        run_dir = Path(args.resume).resolve()
        check_resumable(run_dir, experiment)
    else:
        run_dir = start_run(experiment, config, environ, allow_dirty=args.allow_dirty)
    print(f"run dir     {run_dir}")

    def report(trial, record):
        if record is None:
            print(f"  {trial.trial_id} ...", flush=True)
        else:
            print(f"  {trial.trial_id} {record['status']} reward={record['reward']} "
                  f"{record['runner_wall_clock_s']:.0f}s", flush=True)

    execute(run_dir, experiment, config, environ, limit=args.limit, on_trial=report)
    return 0


def cmd_audit(args) -> int:
    run_dir = Path(args.run_dir).resolve()
    passed, path = write_audit(run_dir, args.partial)
    for check in json.loads(path.read_text())["checks"]:
        print(f"{'PASS' if check['passed'] else 'FAIL'}  {check['name']:<10} {check['detail']}")
        for failure in check["failures"]:
            print(f"        {failure}")
    print(f"audit {'passed' if passed else 'FAILED'}: {path}")
    return 0 if passed else 1


def cmd_report(args) -> int:
    report = build_report(Path(args.run_dir).resolve(), args.partial)
    print(format_report(report))
    return 0 if report["audit_passed"] else 1


def cmd_oracle(args) -> int:
    _, config, experiment, _ = _load(args)
    print(f"oracle      {oracle_dir(experiment, config)}")

    def show(record):
        mark = "FAIL" if failed(record) else "ok  "
        print(f"  {mark} {record['task']} reward={record['reward']} {record['exception_type'] or ''}",
              flush=True)

    results = run_oracle(experiment, config, workers=args.workers,
                         retry_failed=args.retry_failed,
                         only=set(args.tasks.split(",")) if args.tasks else None, on_result=show)
    bad = [r for r in results if failed(r)]
    print(f"{len(results) - len(bad)} of {len(results)} tasks pass their reference solution")
    for r in bad:
        print(f"  exclude? {r['task']}: status={r['status']} reward={r['reward']} "
              f"{r['exception_type'] or ''}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pennybench")
    parser.add_argument("--root", default=".", help="PennyBench repo root")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate an experiment and show its plan")
    check.add_argument("experiment")
    check.set_defaults(func=cmd_check)

    run = sub.add_parser("run", help="run an experiment's trials through Harbor")
    run.add_argument("experiment")
    run.add_argument("--resume", metavar="RUN_DIR")
    run.add_argument("--limit", type=int, metavar="PAIRS", help="run at most this many pairs")
    run.add_argument("--allow-dirty", action="store_true",
                     help="run from an uncommitted tree; the run is marked not pre-registered")
    run.set_defaults(func=cmd_run)

    audit = sub.add_parser("audit", help="check a run's artifacts before any stats")
    audit.add_argument("run_dir")
    audit.add_argument("--partial", action="store_true",
                        help="accept a run stopped before its plan finished (never a claim)")
    audit.set_defaults(func=cmd_audit)

    oracle = sub.add_parser("oracle", help="run every task's reference solution, no model")
    oracle.add_argument("experiment")
    oracle.add_argument("--workers", type=int, default=2)
    oracle.add_argument("--retry-failed", action="store_true",
                        help="rerun tasks whose saved verdict is a failure")
    oracle.add_argument("--tasks", help="comma-separated task names to limit the pass to")
    oracle.set_defaults(func=cmd_oracle)

    report = sub.add_parser("report", help="audit, then compute metrics and paired stats")
    report.add_argument("run_dir")
    report.add_argument("--partial", action="store_true",
                        help="accept a run stopped before its plan finished (never a claim)")
    report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, SpecError, RunError, MetricsError, StatsError, DatasetError,
            AgentCacheError, BuilderError) as exc:
        print(f"pennybench: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
