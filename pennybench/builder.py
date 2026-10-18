"""A dedicated BuildKit builder for task images, with a disk cap on its cache.

Harbor builds each task's image with `docker compose build`, which uses the builder named by
BUILDX_BUILDER. Giving PennyBench its own builder keeps task layers out of the machine's
default build cache, so capping this cache never evicts another project's layers.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


class BuilderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Builder:
    name: str
    cache_cap_gb: float | None

    def env(self) -> dict[str, str]:
        return {"BUILDX_BUILDER": self.name}

    def ensure(self) -> None:
        exists = subprocess.run(["docker", "buildx", "inspect", self.name],
                                capture_output=True, text=True)
        if exists.returncode == 0:
            return
        created = subprocess.run(
            ["docker", "buildx", "create", "--name", self.name, "--driver", "docker-container"],
            capture_output=True, text=True)
        if created.returncode != 0:
            raise BuilderError(f"cannot create buildx builder {self.name!r}: {created.stderr}")

    def enforce_cap(self) -> None:
        """Evict least recently used cache down to the cap. In-use records are never pruned."""
        if self.cache_cap_gb is None:
            return
        out = subprocess.run(
            ["docker", "buildx", "prune", "--builder", self.name, "--force",
             "--max-used-space", f"{int(self.cache_cap_gb * 1024)}mb"],
            capture_output=True, text=True)
        if out.returncode != 0:
            raise BuilderError(f"pruning builder {self.name!r} failed: {out.stderr}")

    def record(self) -> dict:
        return {"name": self.name, "cache_cap_gb": self.cache_cap_gb}
