"""Running an experiment: pre-registration checks, trial execution, and sealing."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from pennybench.agent_cache import ensure_claude_code
from pennybench.artifacts import trial_records
from pennybench.agent_env import build_trial_env
from pennybench.capture import ANTHROPIC_HOST, WireCapture, capture_hosts
from pennybench.claude_login import (StagedLogin, ensure_login, probe_usage, remove_copies,
                                     sweep_leftovers, usage_stop_reason)
from pennybench.harbor_agent import IMPORT_PATH as SIGNED_IN_AGENT
from pennybench.config import LocalConfig
from pennybench.harbor import (harbor_command, harbor_version, run_harbor, sidecar_hosts,
                               task_timeout_s)
from pennybench.hostenv import host_home
from pennybench.plan import PlannedTrial, plan_trials
from pennybench.digest import file_sha256
from pennybench.environment import (record_environment, remove_stray_containers,
                                    remove_stray_images, retire_prebuilt_image)
from pennybench.spec import Arm, Experiment, task_skill_dirs

# Statuses that end a trial for good; anything else is retried on resume.
FINAL_STATUSES = ("complete", "agent_error")

# Exceptions that say nothing about the agent or the setup: the subscription's usage window
# was exhausted, or a transient API limit hit. Such a trial is rerun on resume, not scored.
RETRYABLE_EXCEPTIONS = ("ApiRateLimitError",)
RATE_LIMIT_MARKERS = ("hit your session limit", "hit your usage limit", "rate_limit_error",
                      '"api_error_status":429')


def hit_usage_limit(trial_dir: Path) -> bool:
    """A trial the usage limit ended: Claude Code's own output says so (Harbor reports the
    same failure as ApiRateLimitError or as a non-zero exit, depending on timing)."""
    for log in trial_dir.glob("harbor/*/*/agent/claude-code.txt"):
        tail = log.read_text(errors="replace")[-6000:]
        if any(marker in tail for marker in RATE_LIMIT_MARKERS):
            return True
    return False


class RunError(RuntimeError):
    pass


class UsageLimitError(RunError):
    pass


@dataclass(frozen=True)
class GitState:
    sha: str
    dirty: bool


def git_state(root: Path) -> GitState:
    def git(*args: str) -> str:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        if out.returncode != 0:
            raise RunError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
        return out.stdout.strip()

    return GitState(sha=git("rev-parse", "HEAD"), dirty=bool(git("status", "--porcelain")))


def tree_sha256(directory: Path) -> dict[str, str]:
    return {
        str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*")) if p.is_file()
    }


def find_secret_leaks(directory: Path, secrets: tuple[str, ...]) -> list[str]:
    needles = [s.encode() for s in secrets if s]
    return [
        str(p.relative_to(directory))
        for p in sorted(directory.rglob("*"))
        if p.is_file() and any(n in p.read_bytes() for n in needles)
    ]


def _arm_record(arm: Arm, config: LocalConfig, root: Path) -> dict:
    record = {"id": arm.id, **arm.comparable(root), "adoption_marker": arm.adoption_marker}
    if arm.endpoint_name:
        endpoint = config.endpoint(arm.endpoint_name)
        record["endpoint"] = {"name": endpoint.name, "base_url": endpoint.base_url,
                              "env": endpoint.env}
    record["auth_kind"] = config.auth_profile(arm.auth).kind
    return record


def experiment_capture_hosts(experiment: Experiment, config: LocalConfig) -> list[str]:
    return capture_hosts([config.endpoint(a.endpoint_name).base_url
                          for a in experiment.arms.values() if a.endpoint_name])


def agent_cache_root(config: LocalConfig) -> Path:
    return config.store / ".agents"


# A mounted binary must stay the pinned version for the whole run.
RUNNER_AGENT_ENV = {"DISABLE_AUTOUPDATER": "1"}


def cache_nonce(run_dir: Path, trial: PlannedTrial) -> str:
    """Stable for a run and trial, so a resumed trial sends the same text again."""
    return hashlib.sha256(f"{run_dir.name}/{trial.trial_id}".encode()).hexdigest()[:16]


def cache_isolation_line(nonce: str) -> str:
    return f"(Benchmark trial reference {nonce}; no action needed.)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_run(experiment: Experiment, config: LocalConfig, environ: Mapping[str, str],
              allow_dirty: bool = False) -> Path:
    git = git_state(experiment.root)
    if git.dirty and not allow_dirty:
        raise RunError("working tree is dirty; commit the experiment first so the run is "
                       "pre-registered, or pass --allow-dirty for a run that is not a claim")
    if config.builder:
        config.builder.ensure()
    builds = {}
    for arm in experiment.arms.values():
        build_trial_env(arm, config, environ)
        profile = config.auth_profile(arm.auth)
        if profile.kind == "claude_login":
            ensure_login(profile.min_valid_minutes)
        builds[arm.harness_version] = ensure_claude_code(
            arm.harness_version, agent_cache_root(config)).record()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = config.store / experiment.id / f"{stamp}-{git.sha[:8]}"
    run_dir.mkdir(parents=True)
    manifest = {
        "experiment": experiment.id,
        "experiment_sha256": file_sha256(experiment.source),
        "git_sha": git.sha,
        "git_dirty": git.dirty,
        "preregistered": not git.dirty,
        "created_at": _now(),
        "harbor_version": harbor_version({"PATH": environ.get("PATH", "")}),
        "variable": experiment.variable,
        "tasks": experiment.tasks_source,
        "task_skills": experiment.task_skills,
        "cache_isolation": experiment.cache_isolation,
        "sample": experiment.sample,
        "stage": experiment.stage,
        "k": experiment.k,
        "seed": experiment.seed,
        "task_order": experiment.task_order,
        "cleanup_prebuilt_images": experiment.cleanup_prebuilt_images,
        "endpoints": experiment.endpoints,
        "quality": experiment.quality,
        "task_env": experiment.task_env.record(),
        "exclude": [{"task": e.task, "reason": e.reason} for e in experiment.exclude],
        "arms": {role: _arm_record(arm, config, experiment.root)
                 for role, arm in experiment.arms.items()},
        "agent_builds": builds,
        "task_image_builder": config.builder.record() if config.builder else None,
        "capture_hosts": experiment_capture_hosts(experiment, config),
        "egress_capture": ({"endpoint": e.name, "port": e.egress_capture_port}
                           if (e := egress_endpoint(experiment, config)) else None),
        # The isolation audit looks for this path in request bytes: a hit means host files or
        # config reached the model.
        "host_home": host_home(environ),
        "plan": [t.to_json() for t in plan_trials(experiment)],
    }
    (run_dir / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return run_dir


def check_resumable(run_dir: Path, experiment: Experiment) -> dict:
    manifest = json.loads((run_dir / "run.json").read_text())
    if manifest["experiment_sha256"] != file_sha256(experiment.source):
        raise RunError("experiment file changed since this run started")
    if [t.to_json() for t in plan_trials(experiment)] != manifest["plan"]:
        raise RunError("trial plan differs from the recorded plan")
    # The experiment file, arms, tasks, and plan are what define the measurement, and they are
    # enforced above and below. A different commit (for example a runner fix) is allowed only
    # when it is a clean tree, and is recorded in the run so the report can show it.
    git = git_state(experiment.root)
    if git.dirty:
        raise RunError("resume from a clean, committed tree")
    if git.sha != manifest["git_sha"]:
        manifest.setdefault("resumed_at_commits", []).append(git.sha)
        (run_dir / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def run_trial(trial: PlannedTrial, experiment: Experiment, config: LocalConfig,
              environ: Mapping[str, str], run_dir: Path) -> dict:
    arm = experiment.arms[trial.role]
    task_dir = experiment.tasks / trial.task if experiment.tasks.name != trial.task \
        else experiment.tasks
    trial_dir = run_dir / "trials" / trial.trial_id
    if trial_dir.exists():
        # A previous attempt that did not finish; keep it for inspection, start clean.
        trial_dir.rename(trial_dir.with_name(f"{trial.trial_id}.attempt-{int(time.time())}"))
    trial_dir.mkdir(parents=True)

    skills = task_skill_dirs(task_dir) if experiment.task_skills == "with" else []
    nonce = cache_nonce(run_dir, trial) if experiment.cache_isolation == "trial" else None
    trial_env = build_trial_env(arm, config, environ)
    profile = config.auth_profile(arm.auth)
    login = ensure_login(profile.min_valid_minutes) if profile.kind == "claude_login" else None
    task_host_env, task_secrets = experiment.task_env.host_env(environ)
    secrets = trial_env.secrets + task_secrets + (login.secrets if login else ())
    build = ensure_claude_code(arm.harness_version, agent_cache_root(config))
    capture = WireCapture(trial_dir / "wire", experiment_capture_hosts(experiment, config),
                          config.store / ".mitmproxy")
    capture.start()
    login_record = None
    staged = None
    try:
        # Created inside the try so the copy is always removed, whatever fails after this.
        staged = StagedLogin(login) if login else None
        argv = harbor_command(arm, task_dir, trial_dir / "harbor", trial_env, experiment.root,
                              {**capture.agent_env(tuple(sidecar_hosts(task_dir))), **RUNNER_AGENT_ENV},
                              capture.mounts() + build.mounts()
                              + (staged.mounts() if staged else []), skills,
                              cache_isolation_line(nonce) if nonce else None,
                              agent=SIGNED_IN_AGENT if login else None)
        started = _now()
        t0 = time.monotonic()
        host_env = {**trial_env.host_env, **task_host_env,
                    **(config.builder.env() if config.builder else {})}
        outcome = run_harbor(argv, host_env, trial_dir / "harbor", trial_dir / "harbor.log",
                             timeout_s=task_timeout_s(task_dir))
        wall = time.monotonic() - t0
    finally:
        capture.stop()
        if login:
            try:
                login_record = staged.close(trial_dir) if staged else {}
            finally:
                # Harbor copies Claude Code's config directory back with the logs, login
                # included; those copies go even if syncing a refresh back failed.
                removed = remove_copies(trial_dir)
            login_record["removed_copies"] = removed
            login_record.update(login.plan)
    result = outcome.result or {}
    environment = record_environment(result.get("trial_name"), trial_dir, task_dir)
    remove_stray_images(trial.task)
    remove_stray_containers(trial.task)
    leaks = find_secret_leaks(trial_dir, secrets)
    record = {
        **trial.to_json(),
        "arm": arm.id,
        "status": ("secret_leak" if leaks else
                   "usage_limit" if outcome.status == "agent_error" and hit_usage_limit(trial_dir)
                   else outcome.status),
        "started_at": started,
        "finished_at": _now(),
        "runner_wall_clock_s": round(wall, 3),
        "harbor_exit_code": outcome.exit_code,
        "harbor_hung": outcome.hung,
        "harbor_result": str(outcome.result_path.relative_to(trial_dir))
        if outcome.result_path else None,
        "reward": (result.get("verifier_result") or {}).get("rewards", {}).get("reward"),
        "exception_type": (result.get("exception_info") or {}).get("exception_type"),
        "agent_version": (result.get("agent_info") or {}).get("version"),
        "task_checksum": result.get("task_checksum"),
        "task_skills": [p.name for p in skills],
        "cache_nonce": nonce,
        "login": login_record,
        "environment_sha256": environment["sha256"],
        "environment_error": environment["error"],
        "secret_leaks": leaks,
        "artifacts": tree_sha256(trial_dir),
    }
    (trial_dir / "trial.json").write_text(json.dumps(record, indent=2) + "\n")
    if leaks:
        raise RunError(f"secret found in trial artifacts: {leaks} under {trial_dir}")
    return record


def completed_trials(run_dir: Path) -> set[str]:
    done = set()
    for path in trial_records(run_dir):
        record = json.loads(path.read_text())
        if record["status"] in FINAL_STATUSES:
            done.add(record["trial_id"])
    return done


def egress_endpoint(experiment: Experiment, config: LocalConfig):
    """The proxy endpoint whose own upstream calls are captured, if one is configured."""
    for arm in experiment.arms.values():
        if arm.endpoint_name and config.endpoint(arm.endpoint_name).egress_capture_port:
            return config.endpoint(arm.endpoint_name)
    return None


def start_egress_capture(run_dir: Path, experiment: Experiment,
                         config: LocalConfig) -> WireCapture | None:
    """Capture the proxy's upstream traffic for the whole run. Its calls are matched to trials
    by each trial's cache isolation line, so egress capture requires cache_isolation: trial."""
    endpoint = egress_endpoint(experiment, config)
    if endpoint is None:
        return None
    if experiment.cache_isolation != "trial":
        raise RunError("egress capture needs cache_isolation: trial to attribute calls to trials")
    capture = WireCapture(run_dir / "egress", [ANTHROPIC_HOST], config.store / ".mitmproxy",
                          port=endpoint.egress_capture_port)
    capture.start()
    return capture


def acquire_run_lock(store: Path, run_dir: Path) -> Path:
    """One run at a time per artifact store: runs share the proxy, Docker, the login, and the
    start-of-run sweep of stale login copies, which would delete another run's live copy."""
    lock = store / ".run.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text().split()[0])
            os.kill(pid, 0)
        except (ValueError, IndexError, ProcessLookupError):
            pass  # stale: its process is gone
        except PermissionError:
            pid = None
        else:
            raise RunError(f"another run is active (pid {pid}, {lock.read_text().split(None, 1)[-1]})")
    store.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{os.getpid()} {run_dir}")
    return lock


def execute(run_dir: Path, experiment: Experiment, config: LocalConfig,
            environ: Mapping[str, str], limit: int | None = None,
            on_trial: Callable[[PlannedTrial, dict | None], None] = lambda t, r: None,
            stop_at_utilization: float | None = None) -> None:
    lock = acquire_run_lock(config.store, run_dir)
    try:
        _execute(run_dir, experiment, config, environ, limit, on_trial, stop_at_utilization)
    finally:
        lock.unlink(missing_ok=True)


def _usage_check(experiment: Experiment, config: LocalConfig, threshold: float) -> str | None:
    """Stop reason from the login's current usage, or None to continue. The login is read
    fresh, so a login swapped between trials is the one measured."""
    for arm in experiment.arms.values():
        profile = config.auth_profile(arm.auth)
        if profile.kind == "claude_login":
            return usage_stop_reason(probe_usage(ensure_login(profile.min_valid_minutes)), threshold)
    raise RunError("--stop-at-utilization needs an arm that uses a claude_login auth profile")


def _execute(run_dir: Path, experiment: Experiment, config: LocalConfig,
             environ: Mapping[str, str], limit: int | None,
             on_trial: Callable[[PlannedTrial, dict | None], None],
             stop_at_utilization: float | None = None) -> None:
    sweep_leftovers(run_dir)
    if stop_at_utilization is not None and (reason := _usage_check(
            experiment, config, stop_at_utilization)):
        raise UsageLimitError(f"not starting: {reason}")
    done = completed_trials(run_dir) if (run_dir / "trials").exists() else set()
    pending = [t for t in plan_trials(experiment) if t.trial_id not in done]
    if limit is not None:
        # Whole pairs only, so a partial run never leaves one arm ahead of the other.
        pairs = sorted({t.pair for t in pending})[:limit]
        pending = [t for t in pending if t.pair in pairs]
    if config.builder:
        config.builder.ensure()
    egress = start_egress_capture(run_dir, experiment, config)
    try:
        for trial in pending:
            on_trial(trial, None)
            record = run_trial(trial, experiment, config, environ, run_dir)
            on_trial(trial, record)
            if record["status"] == "usage_limit":
                # Every further trial would fail the same way and burn the window. Stop with
                # the run resumable: this trial is not final, so --resume reruns it.
                raise UsageLimitError(
                    f"subscription usage limit hit at {trial.trial_id}; resume with "
                    f"`pennybench run <experiment> --resume {run_dir}` after the window resets")
            # Both trials of a pair share the task image, so the cache is trimmed between pairs.
            if trial.position == len(experiment.roles) - 1:
                if experiment.cleanup_prebuilt_images:
                    task_dir = (experiment.tasks if experiment.tasks.name == trial.task
                                else experiment.tasks / trial.task)
                    try:
                        retire_prebuilt_image(task_dir)
                    except RuntimeError as exc:
                        raise RunError(str(exc)) from exc
                if config.builder:
                    config.builder.enforce_cap()
                # Only between pairs: both arms of a pair always run on the same login.
                if stop_at_utilization is not None and (reason := _usage_check(
                        experiment, config, stop_at_utilization)):
                    raise UsageLimitError(
                        f"stopping after {trial.trial_id}: {reason}. Switch the Claude Code login "
                        f"if you like, then resume: `pennybench run <experiment> --resume {run_dir}`")
    finally:
        if egress:
            egress.stop()
