"""Content hashes for files and directory trees."""

from __future__ import annotations

import hashlib
from pathlib import Path

IGNORED_NAMES = frozenset({".DS_Store"})


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(directory: Path) -> str:
    """One hash for a directory: sha256 over sorted `relative-path NUL file-sha256 LF` lines."""
    lines = sorted(
        f"{p.relative_to(directory).as_posix()}\0{file_sha256(p)}\n"
        for p in directory.rglob("*") if p.is_file() and p.name not in IGNORED_NAMES
    )
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def content_sha256(path: Path) -> str:
    return tree_sha256(path) if path.is_dir() else file_sha256(path)
