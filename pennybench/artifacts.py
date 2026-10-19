"""Selectors for canonical trial artifacts; retry evidence remains archived."""

from pathlib import Path


def trial_records(run_dir: Path) -> list[Path]:
    return sorted(p for p in (run_dir / "trials").glob("*/trial.json")
                  if ".attempt-" not in p.parent.name)
