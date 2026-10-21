"""Host environment variables that child processes (Harbor, docker) need in order to run."""

from __future__ import annotations

from typing import Mapping

HOST_PASSTHROUGH = (
    "PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL",
    "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT", "SSL_CERT_FILE",
    # Windows: without these Python sockets, docker, and home-directory lookups fail.
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "TEMP", "TMP", "SYSTEMROOT", "SYSTEMDRIVE",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "COMSPEC", "PATHEXT",
)


def host_home(environ: Mapping[str, str]) -> str:
    """The user's home directory as the host names it (HOME, or USERPROFILE on Windows)."""
    return environ.get("HOME") or environ.get("USERPROFILE", "")
