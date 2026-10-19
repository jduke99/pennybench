"""What was installed in a trial's task environment, read from the image Harbor built.

Image digests change on every rebuild even when nothing meaningful changed, so they cannot
show drift. Package versions can: two trials with identical manifests ran in the same
environment. Harbor runs with --no-delete so the image outlives the trial; this module reads
it in a throwaway, network-less container. Shared prebuilt images are retained.
"""

from __future__ import annotations

import hashlib
import subprocess
import tomllib
from pathlib import Path

# Each section prints a header, then one `name==version` / `name=version` line per package.
# Missing tools print nothing, so the same script works on Debian, Ubuntu, and Alpine images.
MANIFEST_SCRIPT = r"""
echo '# python'
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1; then "$py" -m pip list --format=freeze 2>/dev/null; break; fi
done
echo '# dpkg'
command -v dpkg-query >/dev/null 2>&1 && dpkg-query -W -f='${Package}=${Version}\n' 2>/dev/null
echo '# apk'
command -v apk >/dev/null 2>&1 && apk info -v 2>/dev/null
echo '# npm-global'
command -v npm >/dev/null 2>&1 && npm ls -g --depth=0 --parseable=false 2>/dev/null | tail -n +2
true
"""


def trial_image(trial_name: str) -> str:
    """The image Harbor's Docker environment builds for a trial."""
    return f"{trial_name.lower()}__env-main:latest"


def read_manifest(image: str, timeout: float = 180) -> str:
    out = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "--entrypoint", "sh", image,
         "-c", MANIFEST_SCRIPT],
        capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"reading packages from {image} failed: {out.stderr.strip()[:300]}")
    sections, current = {}, None
    for line in out.stdout.splitlines():
        if line.startswith("# "):
            current = line[2:]
            sections[current] = []
        elif line.strip() and current:
            sections[current].append(line.strip())
    # Sorted so the hash depends only on what is installed, not on listing order.
    return "".join(f"# {name}\n" + "".join(f"{p}\n" for p in sorted(pkgs))
                   for name, pkgs in sections.items())


def remove_image(image: str) -> None:
    subprocess.run(["docker", "rmi", "-f", image], capture_output=True, text=True)


def retire_prebuilt_image(task_dir: Path) -> None:
    """Opt-in pair-boundary cleanup of this task's declared image, without force."""
    task = tomllib.loads((task_dir / "task.toml").read_text())
    image = task.get("environment", {}).get("docker_image")
    if not image:
        return
    exists = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    if exists.returncode != 0:
        return
    result = subprocess.run(["docker", "image", "rm", image], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"could not retire task image {image}: {result.stderr.strip()[:300]}")


def remove_stray_images(task_name: str) -> None:
    """Images a crashed Harbor run left for this task. Trials of one task never run
    concurrently, so every such image belongs to the trial that just ended."""
    out = subprocess.run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                         capture_output=True, text=True)
    prefix = f"{task_name.lower()}__"
    for image in out.stdout.split():
        if image.startswith(prefix) and image.endswith("__env-main:latest"):
            remove_image(image)


def remove_stray_containers(task_name: str) -> None:
    """Containers (and networks) a killed Harbor left for this task, by Harbor's naming
    (`<task>__<trial>__env-...`). Trials of one task never run concurrently."""
    name = f"{task_name.lower()}__"
    ids = subprocess.run(["docker", "ps", "-aq", "--filter", f"name={name}"],
                         capture_output=True, text=True).stdout.split()
    if ids:
        subprocess.run(["docker", "rm", "-f", *ids], capture_output=True, text=True)
    nets = subprocess.run(["docker", "network", "ls", "--format", "{{.Name}}"],
                          capture_output=True, text=True).stdout.split()
    for net in [n for n in nets if n.startswith(name)]:
        subprocess.run(["docker", "network", "rm", net], capture_output=True, text=True)


def record_environment(trial_name: str | None, trial_dir: Path,
                       task_dir: Path | None = None) -> dict:
    """Write environment.txt and remove only disposable trial-built images.
    Returns {"sha256", "error"}; a trial whose image was never built has neither."""
    if not trial_name:
        return {"sha256": None, "error": "no Harbor trial"}
    prebuilt = None
    if task_dir is not None:
        task = tomllib.loads((task_dir / "task.toml").read_text())
        prebuilt = task.get("environment", {}).get("docker_image")
    image = prebuilt or trial_image(trial_name)
    exists = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    if exists.returncode != 0:
        return {"sha256": None, "error": "prebuilt image unavailable" if prebuilt else "image was not built"}
    try:
        manifest = read_manifest(image)
        (trial_dir / "environment.txt").write_text(manifest)
        return {"sha256": hashlib.sha256(manifest.encode()).hexdigest(), "error": None}
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        return {"sha256": None, "error": str(exc)[:300]}
    finally:
        if not prebuilt:
            remove_image(image)
