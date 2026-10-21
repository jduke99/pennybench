"""Environment a task's own services need, kept apart from the agent's.

Some tasks run model-backed services next to the agent, such as a user simulator or an LLM
grader. Their credentials and settings reach Harbor's host environment, where the task's
`${NAME}` templates resolve them. They never reach the agent's `--ae` environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pennybench.config import ConfigError


@dataclass(frozen=True)
class TaskEnv:
    # Names of host variables copied through to Harbor; their values are secrets.
    secrets: tuple[str, ...] = ()
    # Fixed, non-secret settings, recorded in the run manifest so the task's defaults
    # cannot change the measurement silently.
    values: Mapping[str, str] = None

    def record(self) -> dict:
        return {"secrets": list(self.secrets), "values": dict(self.values or {})}

    def host_env(self, environ: Mapping[str, str]) -> tuple[dict[str, str], tuple[str, ...]]:
        """The variables Harbor's process receives, and the secret values to scan for."""
        env = dict(self.values or {})
        for name in self.secrets:
            if not environ.get(name):
                raise ConfigError(f"task_env needs ${name}, which is not set")
            env[name] = environ[name]
        return env, tuple(environ[name] for name in self.secrets)


def parse_task_env(raw: Any, where: object) -> TaskEnv:
    from pennybench.agent_env import RESERVED_AGENT_VARS  # agent_env imports spec
    from pennybench.spec import SpecError

    raw = raw or {}
    secrets, values = raw.get("secrets") or [], raw.get("values") or {}
    if (not isinstance(raw, dict) or set(raw) - {"secrets", "values"}
            or not isinstance(secrets, list) or not isinstance(values, dict)):
        raise SpecError(f"{where}: task_env is {{secrets: [NAME, ...], values: {{NAME: value}}}}")
    names = [*map(str, secrets), *map(str, values)]
    clash = RESERVED_AGENT_VARS & set(names)
    if clash:
        raise SpecError(f"{where}: task_env may not set agent variables {sorted(clash)}")
    if len(set(names)) != len(names):
        raise SpecError(f"{where}: task_env names a variable twice")
    return TaskEnv(secrets=tuple(map(str, secrets)),
                   values={str(k): str(v) for k, v in values.items()})
