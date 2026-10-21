import os
import subprocess
import sys

import pytest

from pennybench.agent_cache import CONTAINER_DIR, LAUNCHER


@pytest.mark.skipif(sys.platform == "win32", reason="runs the POSIX sh launcher; covered in WSL")
@pytest.mark.parametrize("machine,arch", [("x86_64", "x64"), ("aarch64", "arm64")])
@pytest.mark.parametrize("musl", [False, True])
def test_launcher_uses_container_architecture_and_libc(tmp_path, machine, arch, musl):
    binaries = tmp_path / "binaries"
    for platform in ("linux-arm64", "linux-x64", "linux-arm64-musl", "linux-x64-musl"):
        path = binaries / platform / "claude"
        path.parent.mkdir(parents=True)
        path.write_text(f'#!/bin/sh\necho {platform}\n')
        path.chmod(0o755)
    commands = tmp_path / "bin"
    commands.mkdir()
    for name, text in {"uname": f"echo {machine}", "ldd": "echo musl" if musl else "echo glibc"}.items():
        path = commands / name
        path.write_text(f"#!/bin/sh\n{text}\n")
        path.chmod(0o755)
    launcher = tmp_path / "launcher.sh"
    launcher.write_text(LAUNCHER.replace(CONTAINER_DIR, str(binaries)))
    result = subprocess.run(["sh", str(launcher)], capture_output=True, text=True, check=True,
                            env={"PATH": f"{commands}:{os.defpath}"})
    assert result.stdout.strip() == f"linux-{arch}" + ("-musl" if musl else "")
