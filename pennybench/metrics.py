"""Per-trial endpoint values, computed only from a trial's sealed artifacts."""

from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pennybench.wire import ModelCall, model_calls, read_capture, usage_totals

RATES_PATH = Path(__file__).with_name("rates.json")

# Every endpoint an experiment may name. `reward` is compared with a sign test; the rest as
# paired ratios.
METRICS = (
    "reward", "cost", "total_tokens", "output_tokens", "fresh_input_tokens",
    "cache_read_tokens", "cache_write_tokens", "loc_written", "turns", "wall_clock",
    "gateway_overhead_cost", "cost_all_in",
)

COMMENT_PREFIXES = ("#", "//", "/*", "*", "--", "<!--")
_HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
_REDIRECT = re.compile(r"(^|[\s;|&])(>>?|tee(\s+-a)?)\s*[^\s&|>]")


class MetricsError(ValueError):
    pass


@lru_cache(maxsize=1)
def rate_table() -> dict:
    return json.loads(RATES_PATH.read_text())


def call_cost(call: ModelCall) -> float:
    """Notional USD for one model call at the pinned rates. A model the table does not
    list is an error, never a zero."""
    table = rate_table()
    model = (call.responded_model or call.requested_model or "").removeprefix("anthropic/")
    model = model.removesuffix("[1m]")
    if model not in table["models"]:
        raise MetricsError(f"no pinned rate for model {model!r} (rates {table['version']})")
    entry = table["models"][model]
    u = call.usage
    fresh = u.get("input_tokens", 0)
    read = u.get("cache_read_input_tokens", 0)
    write = u.get("cache_creation_input_tokens", 0)
    w1h = u.get("ephemeral_1h_input_tokens", 0)
    w5m = write - w1h
    rates = entry["rates"]
    above = entry.get("above")
    if above and fresh + read + write > above["threshold"]:
        rates = above["rates"]
    inp, rd, r5, r1, out = rates
    return fresh * inp + read * rd + w5m * r5 + w1h * r1 + u.get("output_tokens", 0) * out


def code_lines(text: str) -> int:
    """Non-blank lines that are not comment-only."""
    return sum(1 for line in text.splitlines()
               if line.strip() and not line.strip().startswith(COMMENT_PREFIXES))


def heredoc_file_lines(command: str) -> int:
    """Lines of heredocs whose output is written to a file. Heredocs fed to an interpreter
    produce no file and count as scratch work, not code."""
    lines = command.splitlines()
    total, i = 0, 0
    while i < len(lines):
        match = _HEREDOC.search(lines[i])
        if not match:
            i += 1
            continue
        opener = lines[i][:match.start()] + lines[i][match.end():]
        end = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == match.group(1)),
                   len(lines))
        if _REDIRECT.search(opener):
            total += code_lines("\n".join(lines[i + 1:end]))
        i = end + 1
    return total


def tool_use_lines(use: dict) -> int:
    name, args = use.get("name"), use.get("input")
    if not isinstance(args, dict):
        return 0
    if name == "Write":
        return code_lines(args.get("content") or "")
    if name == "Edit":
        return code_lines(args.get("new_string") or "")
    if name == "MultiEdit":
        return sum(code_lines(e.get("new_string") or "") for e in args.get("edits") or [])
    if name == "NotebookEdit":
        return code_lines(args.get("new_source") or "")
    if name == "Bash":
        return heredoc_file_lines(args.get("command") or "")
    return 0


def _seconds(span: dict | None) -> float | None:
    if not span or not span.get("started_at") or not span.get("finished_at"):
        return None
    start = datetime.fromisoformat(span["started_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(span["finished_at"].replace("Z", "+00:00"))
    return (end - start).total_seconds()


def egress_calls_for(nonce: str | None, egress: list[ModelCall]) -> list[ModelCall]:
    return [c for c in egress if nonce and nonce in c.request_text]


def trial_metrics(trial_dir: Path, egress: list[ModelCall] | None = None) -> dict:
    """`egress`: the run's proxy-upstream calls, when captured. A trial's share is the calls
    carrying its isolation line; what they cost beyond the calls the agent itself made is the
    proxy's overhead (keepalive pings, retries)."""
    record = json.loads((trial_dir / "trial.json").read_text())
    calls = model_calls(read_capture(trial_dir / "wire" / "wire.jsonl"))
    totals = usage_totals(calls)
    harbor = {}
    if record.get("harbor_result"):
        harbor = json.loads((trial_dir / record["harbor_result"]).read_text())
    values = {
        "reward": record.get("reward"),
        "cost": sum(call_cost(c) for c in calls),
        "total_tokens": totals["total_tokens"],
        "output_tokens": totals["output_tokens"],
        "fresh_input_tokens": totals["input_tokens"],
        "cache_read_tokens": totals["cache_read_input_tokens"],
        "cache_write_tokens": totals["cache_creation_input_tokens"],
        "loc_written": sum(tool_use_lines(u) for c in calls for u in c.tool_uses),
        "turns": len(calls),
        # Agent execution only: container build and agent install are not the agent's work.
        "wall_clock": _seconds(harbor.get("agent_execution")),
        "gateway_overhead_cost": None,
        "cost_all_in": None,
    }
    if egress is not None:
        upstream = egress_calls_for(record.get("cache_nonce"), egress)
        overhead = sum(call_cost(c) for c in upstream) - values["cost"] if upstream else 0.0
        values["gateway_overhead_cost"] = overhead
        values["cost_all_in"] = values["cost"] + overhead
    return {
        "trial_id": record["trial_id"],
        "task": record["task"],
        "rep": record["rep"],
        "role": record["role"],
        "status": record["status"],
        "rates_version": rate_table()["version"],
        "metrics": values,
    }


def run_egress(run_dir: Path) -> list[ModelCall] | None:
    path = run_dir / "egress" / "wire.jsonl"
    return model_calls(read_capture(path)) if path.parent.exists() else None


def run_metrics(run_dir: Path) -> list[dict]:
    egress = run_egress(run_dir)
    return [trial_metrics(p.parent, egress)
            for p in sorted((run_dir / "trials").glob("*/trial.json"))]


def unattributed_egress(run_dir: Path) -> dict | None:
    """Proxy upstream calls that carry no trial's isolation line (e.g. compaction), which the
    report shows as a run-level cost rather than charging to any trial."""
    egress = run_egress(run_dir)
    if egress is None:
        return None
    nonces = [json.loads(p.read_text()).get("cache_nonce")
              for p in (run_dir / "trials").glob("*/trial.json")]
    loose = [c for c in egress if not any(n and n in c.request_text for n in nonces)]
    return {"calls": len(loose), "cost": sum(call_cost(c) for c in loose),
            "models": sorted({(c.responded_model or c.requested_model or "?") for c in loose})}
