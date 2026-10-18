"""Wire capture: one mitmdump forward proxy per trial, in the agent's egress path.

Both arms go through the same kind of capture point, so every measured token comes from the
same vantage. The agent keeps its own endpoint: the proxy intercepts TLS only for the capture
hosts and tunnels everything else (package installs, downloads) untouched.
"""

from __future__ import annotations

import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ADDON = Path(__file__).with_name("capture_addon.py")
ANTHROPIC_HOST = "api.anthropic.com"
CONTAINER_CA_PATH = "/pennybench/ca.pem"
DOCKER_HOST_ALIAS = "host.docker.internal"


class CaptureError(RuntimeError):
    pass


def endpoint_host(base_url: str) -> str:
    host = urlparse(base_url).hostname
    if not host:
        raise CaptureError(f"cannot read a host from {base_url!r}")
    return host


def capture_hosts(base_urls: list[str]) -> list[str]:
    """Anthropic plus every endpoint either arm can reach. Both arms capture the same set, so a
    request that bypasses its declared route is still recorded."""
    return sorted({ANTHROPIC_HOST, *(endpoint_host(u) for u in base_urls)})


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class WireCapture:
    def __init__(self, directory: Path, hosts: list[str], confdir: Path):
        self.directory = directory
        self.hosts = hosts
        self.confdir = confdir
        self.port = _free_port()
        self.capture_file = directory / "wire.jsonl"
        self.log = directory / "mitmdump.log"
        self.process: subprocess.Popen | None = None

    @property
    def ca_cert(self) -> Path:
        return self.confdir / "mitmproxy-ca-cert.pem"

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.confdir.mkdir(parents=True, exist_ok=True)
        allow = "|".join(re.escape(h) for h in self.hosts)
        command = [
            str(Path(sys.executable).with_name("mitmdump")),
            "--listen-host", "127.0.0.1",
            "--listen-port", str(self.port),
            "--set", f"confdir={self.confdir}",
            "--set", "block_global=false",
            "--set", f"allow_hosts=^({allow})(:\\d+)?$",
            "-s", str(ADDON),
            "--set", f"pb_capture_file={self.capture_file}",
            "--set", f"pb_capture_hosts={','.join(self.hosts)}",
            # The Mac host cannot resolve Docker's alias for itself; the proxy runs on the host.
            "--set", f"pb_host_rewrites={DOCKER_HOST_ALIAS}=127.0.0.1",
        ]
        self.process = subprocess.Popen(command, stdout=self.log.open("wb"),
                                        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        if not self._await_listening() or not self.ca_cert.exists():
            self.stop()
            raise CaptureError(f"mitmdump did not start; see {self.log}")

    def _await_listening(self, timeout: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                return False
            with socket.socket() as probe:
                probe.settimeout(0.5)
                if probe.connect_ex(("127.0.0.1", self.port)) == 0:
                    return True
            time.sleep(0.2)
        return False

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def agent_env(self) -> dict[str, str]:
        proxy = f"http://{DOCKER_HOST_ALIAS}:{self.port}"
        return {
            "HTTPS_PROXY": proxy,
            "HTTP_PROXY": proxy,
            "NODE_EXTRA_CA_CERTS": CONTAINER_CA_PATH,
        }

    def mounts(self) -> list[dict]:
        return [{"type": "bind", "source": str(self.ca_cert), "target": CONTAINER_CA_PATH,
                 "read_only": True}]
