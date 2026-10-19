"""Selectors for canonical trial artifacts; retry evidence remains archived."""

from pathlib import Path
import re


def trial_records(run_dir: Path) -> list[Path]:
    return sorted(p for p in (run_dir / "trials").glob("*/trial.json")
                  if not re.search(r"\.attempt-\d+$", p.parent.name))
