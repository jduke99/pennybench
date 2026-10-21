"""Prebuilt Claude Code binaries, mounted into every trial instead of installed per trial.

Harbor skips its install step when `claude --version` in the container already matches the
pinned version. Mounting the official release binary achieves that without touching any task's
image, so the environment under test stays exactly as the task defines it.

Binaries come from the same release bucket and manifest the official installer uses, and each
is checked against the manifest's sha256 before use.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RELEASES = "https://downloads.claude.ai/claude-code-releases"
CONTAINER_DIR = "/pennybench/claude-code"
CONTAINER_LAUNCHER = "/usr/local/bin/claude"

# Picks the glibc or musl build the same way the official installer does.
LAUNCHER = f"""#!/bin/sh
case "$(uname -m)" in
  x86_64|amd64) arch=x64 ;;
  aarch64|arm64) arch=arm64 ;;
  *) echo "unsupported container architecture" >&2; exit 1 ;;
esac
if [ -f /lib/libc.musl-x86_64.so.1 ] || [ -f /lib/libc.musl-aarch64.so.1 ] || \\
   ldd /bin/ls 2>&1 | grep -q musl; then
  exec {CONTAINER_DIR}/linux-$arch-musl/claude "$@"
fi
exec {CONTAINER_DIR}/linux-$arch/claude "$@"
"""


class AgentCacheError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaudeCodeBuild:
    version: str
    arch: str
    directory: Path
    checksums: dict[str, str]

    @property
    def launcher(self) -> Path:
        return self.directory / "launcher.sh"

    def mounts(self) -> list[dict]:
        return [
            {"type": "bind", "source": str(self.directory), "target": CONTAINER_DIR,
             "read_only": True},
            {"type": "bind", "source": str(self.launcher), "target": CONTAINER_LAUNCHER,
             "read_only": True},
        ]

    def record(self) -> dict:
        return {"version": self.version, "arch": self.arch, "sha256": self.checksums}


def docker_arch() -> str:
    out = subprocess.run(["docker", "info", "--format", "{{.Architecture}}"],
                         capture_output=True, text=True)
    machine = out.stdout.strip()
    arch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(machine)
    if not arch:
        raise AgentCacheError(f"cannot map Docker architecture {machine!r}; is Docker running?")
    return arch


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=300) as response, tmp.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    tmp.replace(dest)


def ensure_claude_code(version: str, cache_root: Path, arch: str | None = None) -> ClaudeCodeBuild:
    # A dataset can mix native arm64 and emulated x64 images on the same daemon.
    # Cache both by default; the launcher chooses from inside the task container.
    arch = arch or "multi"
    directory = cache_root / "claude-code" / version
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        _download(f"{RELEASES}/{version}/manifest.json", manifest_path)
    platforms = json.loads(manifest_path.read_text()).get("platforms", {})

    checksums = {}
    architectures = ("arm64", "x64") if arch == "multi" else (arch,)
    for platform in [p for a in architectures for p in (f"linux-{a}", f"linux-{a}-musl")]:
        if platform not in platforms:
            raise AgentCacheError(f"Claude Code {version} has no {platform} build")
        expected = platforms[platform]["checksum"]
        binary = directory / platform / "claude"
        binary.parent.mkdir(exist_ok=True)
        if not binary.exists() or _sha256(binary) != expected:
            _download(f"{RELEASES}/{version}/{platform}/claude", binary)
        actual = _sha256(binary)
        if actual != expected:
            binary.unlink()
            raise AgentCacheError(f"{platform} checksum mismatch: {actual} != {expected}")
        binary.chmod(0o755)
        checksums[platform] = actual

    build = ClaudeCodeBuild(version=version, arch=arch, directory=directory, checksums=checksums)
    build.launcher.write_text(LAUNCHER, newline="\n")
    build.launcher.chmod(0o755)
    return build
