"""`pennybench` command line."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pennybench.agent_env import build_trial_env
from pennybench.config import LOCAL_CONFIG_NAME, ConfigError, load_local_config
from pennybench.plan import plan_trials
from pennybench.run import RunError, check_resumable, execute, start_run
from pennybench.spec import SpecError, load_experiment


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
    experiment = load_experiment(Path(args.experiment).resolve(), root)
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

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, SpecError, RunError) as exc:
        print(f"pennybench: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
