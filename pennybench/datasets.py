"""Registry datasets, downloaded once per pinned ref and verified by content hash."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from pennybench.digest import tree_sha256


class DatasetError(RuntimeError):
    pass


def dataset_dir(ref: str, store: Path) -> Path:
    if "@" not in ref or ref.endswith("@latest"):
        raise DatasetError(f"dataset {ref!r} must name a fixed ref, e.g. org/name@v1.1")
    return store / ref.replace("/", "__")


def ensure_dataset(ref: str, sha256: str, store: Path) -> Path:
    """The dataset's task directory, downloaded if absent. Content must match `sha256`."""
    from pennybench.harbor import harbor_bin  # harbor imports spec, which imports this module

    target = dataset_dir(ref, store)
    if not target.exists():
        staging = target.with_name(target.name + ".part")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
        out = subprocess.run([harbor_bin(), "download", ref, "-o", str(staging)], env=env,
                             capture_output=True, text=True)
        children = [p for p in staging.iterdir() if p.is_dir()]
        if out.returncode != 0 or len(children) != 1:
            raise DatasetError(f"harbor download {ref} failed:\n{out.stdout}\n{out.stderr}")
        children[0].rename(target)
        shutil.rmtree(staging)
    actual = tree_sha256(target)
    if actual != sha256:
        raise DatasetError(f"{ref} at {target} has content {actual}, expected {sha256}")
    return target
