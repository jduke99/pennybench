"""Launching one Harbor trial and reading back what it produced."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pennybench.agent_env import TrialEnv
from pennybench.spec import Arm


def harbor_bin() -> str:
    beside = Path(sys.executable).with_name("harbor")
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


@dataclass(frozen=True)
class HarborOutcome:
    exit_code: int
    result_path: Path | None
    result: dict | None

    @property
    def status(self) -> str:
        if self.result is None:
            return "harbor_failed"
        return "agent_error" if self.result.get("exception_info") else "complete"


def run_harbor(argv: list[str], host_env: dict[str, str], out_dir: Path,
               log_path: Path) -> HarborOutcome:
    out_dir.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log:
        proc = subprocess.run(argv, env=host_env, stdout=log, stderr=subprocess.STDOUT)
    results = sorted(out_dir.glob("*/*/result.json"))
    if not results:
        return HarborOutcome(proc.returncode, None, None)
    if len(results) > 1:
        raise RuntimeError(f"expected one Harbor trial result under {out_dir}, found {len(results)}")
    return HarborOutcome(proc.returncode, results[0], json.loads(results[0].read_text()))
