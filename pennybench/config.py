"""Local, deployment-specific configuration (`pennybench.local.toml`).

Tracked files name endpoints and auth profiles; only this file says where they point and
which environment variables hold their secrets. Secrets themselves stay in the environment.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

LOCAL_CONFIG_NAME = "pennybench.local.toml"

AUTH_KINDS = ("oauth", "api_key")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Endpoint:
    name: str
    base_url: str
    key_env: str | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthProfile:
    name: str
    kind: str
    token_env: str


@dataclass(frozen=True)
class LocalConfig:
    store: Path
    endpoints: dict[str, Endpoint]
    auth: dict[str, AuthProfile]

    def endpoint(self, name: str) -> Endpoint:
        if name not in self.endpoints:
            raise ConfigError(f"endpoint {name!r} is not defined in {LOCAL_CONFIG_NAME}")
        return self.endpoints[name]

    def auth_profile(self, name: str) -> AuthProfile:
        if name not in self.auth:
            raise ConfigError(f"auth profile {name!r} is not defined in {LOCAL_CONFIG_NAME}")
        return self.auth[name]


def load_local_config(path: Path) -> LocalConfig:
    if not path.exists():
        raise ConfigError(f"{path} not found; copy config.example.toml to {LOCAL_CONFIG_NAME}")
    raw = tomllib.loads(path.read_text())

    store = Path(raw.get("artifacts", {}).get("store", "runs")).expanduser()
    if not store.is_absolute():
        store = path.parent / store

    endpoints = {}
    for name, spec in raw.get("endpoints", {}).items():
        if "base_url" not in spec:
            raise ConfigError(f"endpoint {name!r} needs base_url")
        endpoints[name] = Endpoint(
            name=name,
            base_url=spec["base_url"],
            key_env=spec.get("key_env"),
            env={k: str(v) for k, v in spec.get("env", {}).items()},
        )

    auth = {}
    for name, spec in raw.get("auth", {}).items():
        kind = spec.get("kind")
        if kind not in AUTH_KINDS:
            raise ConfigError(f"auth profile {name!r} needs kind = one of {AUTH_KINDS}")
        if "token_env" not in spec:
            raise ConfigError(f"auth profile {name!r} needs token_env")
        auth[name] = AuthProfile(name=name, kind=kind, token_env=spec["token_env"])

    return LocalConfig(store=store, endpoints=endpoints, auth=auth)
