"""The environment a trial runs in, built from the arm spec alone.

Harbor forwards host ANTHROPIC_* variables into the agent, so Harbor itself runs with a
minimal host environment and nothing inherited from the caller's shell. Secrets reach Harbor
under private names and are referenced from `--ae` as `${NAME}` templates, which Harbor
resolves at launch. Secret values therefore never appear in argv or in Harbor's saved config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pennybench.config import ConfigError, LocalConfig
from pennybench.spec import Arm

HOST_PASSTHROUGH = (
    "PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL",
    "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT", "SSL_CERT_FILE",
)

UPSTREAM_SECRET = "PENNYBENCH_SECRET_UPSTREAM"
ENDPOINT_SECRET = "PENNYBENCH_SECRET_ENDPOINT"

# Variables the route and auth logic owns; an endpoint's extra env may not set them.
RESERVED_AGENT_VARS = frozenset({
    "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
})


@dataclass(frozen=True)
class TrialEnv:
    agent_env: dict[str, str]
    host_env: dict[str, str]
    secrets: tuple[str, ...]


def _secret(environ: Mapping[str, str], name: str, purpose: str) -> str:
    value = environ.get(name, "")
    if not value:
        raise ConfigError(f"{purpose} needs ${name}, which is not set")
    return value


def build_trial_env(arm: Arm, config: LocalConfig, environ: Mapping[str, str]) -> TrialEnv:
    profile = config.auth_profile(arm.auth)
    upstream = _secret(environ, profile.token_env, f"auth profile {profile.name!r}")
    secret_vars = {UPSTREAM_SECRET: upstream}
    upstream_ref = f"${{{UPSTREAM_SECRET}}}"

    agent_env: dict[str, str] = {}
    if arm.endpoint_name is None:
        if profile.kind == "oauth":
            agent_env["CLAUDE_CODE_OAUTH_TOKEN"] = upstream_ref
        else:
            agent_env["ANTHROPIC_API_KEY"] = upstream_ref
    else:
        endpoint = config.endpoint(arm.endpoint_name)
        agent_env["ANTHROPIC_BASE_URL"] = endpoint.base_url
        if profile.kind == "oauth":
            # The upstream subscription token travels as the bearer; the endpoint's own
            # key, if it has one, identifies the caller as x-api-key.
            agent_env["ANTHROPIC_AUTH_TOKEN"] = upstream_ref
            if endpoint.key_env:
                secret_vars[ENDPOINT_SECRET] = _secret(
                    environ, endpoint.key_env, f"endpoint {endpoint.name!r}")
                agent_env["ANTHROPIC_API_KEY"] = f"${{{ENDPOINT_SECRET}}}"
        else:
            if endpoint.key_env:
                raise ConfigError(
                    f"endpoint {endpoint.name!r} has its own key, which would collide with "
                    f"api_key profile {profile.name!r} on x-api-key")
            agent_env["ANTHROPIC_API_KEY"] = upstream_ref
        clash = RESERVED_AGENT_VARS & set(endpoint.env)
        if clash:
            raise ConfigError(f"endpoint {endpoint.name!r} env may not set {sorted(clash)}")
        agent_env.update(endpoint.env)

    host_env = {k: environ[k] for k in HOST_PASSTHROUGH if environ.get(k)}
    host_env.update(secret_vars)
    return TrialEnv(agent_env=agent_env, host_env=host_env, secrets=tuple(secret_vars.values()))
