"""Observe terminal Claude results without treating them as verifier rewards."""
from __future__ import annotations

import json
from pathlib import Path


def terminal_result(path: Path) -> dict | None:
    """Ignore partial JSONL writes and nonterminal/intermediate records."""
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if (isinstance(record, dict) and record.get('type') == 'result'
                and record.get('terminal_reason') in {'completed', 'api_error'}):
            return record
    return None
