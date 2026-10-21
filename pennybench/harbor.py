"""Launching one Harbor trial and reading back what it produced."""

from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import tomllib
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path

from pennybench.agent_env import TrialEnv
from pennybench.spec import Arm


def harbor_bin() -> str:
    beside = Path(sys.executable).with_name("harbor.exe" if sys.platform == "win32" else "harbor")
    if beside.exists():
        return str(beside)
    found = shutil.which("harbor")
    if not found:
        raise FileNotFoundError("harbor CLI not found; install the pennybench environment")
    return found


def harbor_version(env: dict[str, str]) -> str:
    out = subprocess.run([harbor_bin(), "--version"], env=env, capture_output=True, text=True)
    return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "unknown"


def harbor_command(arm: Arm, task_dir: Path, out_dir: Path, trial_env: TrialEnv,
                   root: Path, runner_env: dict[str, str],
                   mounts: list[dict], task_skills: list[Path] = (),
                   instruction_suffix: str | None = None,
                   agent: str | None = None) -> list[str]:
    """`runner_env` is what PennyBench itself sets in every trial (capture proxy, updater
    off); an arm may not override it."""
    clash = set(runner_env) & set(trial_env.agent_env)
    if clash:
        raise ValueError(f"arm env sets runner variables {sorted(clash)}")
    argv = [
        harbor_bin(), "run",
        "-p", str(task_dir),
        # A Harbor agent import path replaces the stock adapter for the same harness.
        "-a", agent or arm.harness,
        # Bare id: Harbor keeps a provider prefix only when a base URL is set, which would make
        # the two routes send different model strings.
        "-m", arm.model,
        "-o", str(out_dir),
        "-n", "1",
        # Tasks that read host variables (a user simulator's key) ask before launching.
        "--yes",
        # Keep the built image so the runner can record its packages; the runner removes it.
        "--no-delete",
        "--ak", f"version={arm.harness_version}",
    ]
    if arm.effort:
        argv += ["--ak", f"reasoning_effort={arm.effort}"]
    if "append_system_prompt_file" in arm.inject:
        text = (root / arm.inject["append_system_prompt_file"]).read_text()
        argv += ["--ak", f"append_system_prompt={text}"]
    if "instruction_append_file" in arm.inject:
        argv += ["--extra-instruction-path", str(root / arm.inject["instruction_append_file"])]
    for skill in task_skills:
        argv += ["--skill", str(skill)]
    if "skills_dir" in arm.inject:
        argv += ["--skill", str(root / arm.inject["skills_dir"])]
    if instruction_suffix:
        # Appended after any --extra-instruction-path files.
        argv += ["--extra-instruction", instruction_suffix]
    if "settings_file" in arm.inject:
        argv += ["--ak", f"config={root / arm.inject['settings_file']}"]
    for key, value in sorted({**trial_env.agent_env, **runner_env}.items()):
        argv += ["--ae", f"{key}={value}"]
    if mounts:
        argv += ["--mounts", json.dumps(mounts)]
    return argv


# Harbor's timeouts depend on `docker compose` calls returning; when one wedges,
# they may never fire. Keep a one-hour minimum for the process backstop.
TRIAL_TIMEOUT_S = 3600


def sidecar_hosts(task_dir: Path) -> list[str]:
    """Hosts of the MCP servers a task declares. They are the task's own services, reachable
    only inside its network, so the agent must not send them through the capture proxy."""
    task = tomllib.loads((task_dir / "task.toml").read_text())
    servers = task.get("environment", {}).get("mcp_servers", [])
    return sorted({h for s in servers if (h := urlparse(s.get("url", "")).hostname)})


def task_timeout_s(task_dir: Path) -> float:
    """Backstop beyond build, setup, agent and verifier limits, plus teardown slack.

    Harbor's own limits remain unchanged. 360 seconds allows agent setup and
    600 seconds allows orchestration/cleanup. Tasks without an agent limit
    retain the existing one-hour backstop.
    """
    task = tomllib.loads((task_dir / "task.toml").read_text())
    build = task.get("environment", {}).get("build_timeout_sec", 600)
    agent = task.get("agent", {}).get("timeout_sec")
    if agent is None:
        return TRIAL_TIMEOUT_S
    verifier = task.get("verifier", {}).get("timeout_sec", 600)
    return max(TRIAL_TIMEOUT_S, build + 360 + agent + verifier + 600)


@dataclass(frozen=True)
class HarborOutcome:
    exit_code: int
    result_path: Path | None
    result: dict | None
    # Harbor did not finish within the cap and was killed; the trial is incomplete.
    hung: bool = False

    @property
    def status(self) -> str:
        if self.result is None or self.hung:
            return "harbor_failed"
        return "agent_error" if self.result.get("exception_info") else "complete"


def _stop_tree(proc: subprocess.Popen, force: bool) -> None:
    """Stop Harbor and the docker compose calls it spawned."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGKILL if force else signal.SIGTERM)


def run_harbor(argv: list[str], host_env: dict[str, str], out_dir: Path,
               log_path: Path, timeout_s: float = TRIAL_TIMEOUT_S) -> HarborOutcome:
    out_dir.mkdir(parents=True, exist_ok=True)
    hung = False
    with log_path.open("w") as log:
        # Its own session (process group on Windows), so a timeout can kill Harbor together
        # with the docker compose calls it spawned.
        group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32"
                 else {"start_new_session": True})
        proc = subprocess.Popen(argv, env=host_env, stdout=log, stderr=subprocess.STDOUT, **group)
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            hung = True
            _stop_tree(proc, force=False)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                _stop_tree(proc, force=True)
                proc.wait()
    if hung:
        return HarborOutcome(proc.returncode, None, None, hung=True)
    results = sorted(out_dir.glob("*/*/result.json"))
    if not results:
        return HarborOutcome(proc.returncode, None, None)
    if len(results) > 1:
        raise RuntimeError(f"expected one Harbor trial result under {out_dir}, found {len(results)}")
    return HarborOutcome(proc.returncode, results[0], json.loads(results[0].read_text()))
