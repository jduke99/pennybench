"""Reading a trial's wire capture: model calls and the usage each response reported."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

USAGE_FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                "output_tokens")
# The 5-minute and 1-hour cache-write tiers are priced differently; Anthropic reports the
# split under usage.cache_creation.
WRITE_TIER_FIELDS = ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")


@dataclass(frozen=True)
class ModelCall:
    seq: int
    host: str
    path: str
    status: int | None
    requested_model: str | None
    responded_model: str | None
    usage: dict[str, int] = field(default_factory=dict)
    tool_uses: list[dict] = field(default_factory=list)
    request_text: str = ""
    error: str | None = None


def is_model_call(record: dict) -> bool:
    path = record.get("path") or ""
    return (record.get("method") == "POST" and path.startswith("/v1/messages")
            and not path.startswith("/v1/messages/count_tokens"))


def _sse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            events.append(json.loads(line[5:].strip()))
        except ValueError:
            continue
    return events


def _usage_fields(source: dict) -> dict[str, int]:
    found = {k: int(source[k]) for k in USAGE_FIELDS if source.get(k) is not None}
    tiers = source.get("cache_creation") or {}
    found.update({k: int(tiers[k]) for k in WRITE_TIER_FIELDS if tiers.get(k) is not None})
    return found


def response_usage(body: object) -> tuple[str | None, dict[str, int]]:
    """Model and final usage from a Messages response, streamed (SSE text) or not (JSON).
    In a stream, message_start carries the input side and message_delta the final output
    count; later non-null values win."""
    if isinstance(body, dict):
        return body.get("model"), _usage_fields(body.get("usage") or {})
    if not isinstance(body, str):
        return None, {}
    model, usage = None, {}
    for event in _sse_events(body):
        if event.get("type") == "message_start":
            message = event.get("message") or {}
            model = message.get("model") or model
            usage.update(_usage_fields(message.get("usage") or {}))
        elif event.get("type") == "message_delta":
            usage.update(_usage_fields(event.get("usage") or {}))
    return model, usage


def response_tool_uses(body: object) -> list[dict]:
    """Tool calls the model made, as {"name", "input"}; streamed inputs are reassembled from
    their input_json_delta fragments. An input that does not parse is kept as raw text."""
    if isinstance(body, dict):
        return [{"name": b.get("name"), "input": b.get("input")}
                for b in body.get("content") or [] if b.get("type") == "tool_use"]
    if not isinstance(body, str):
        return []
    blocks: dict[int, dict] = {}
    for event in _sse_events(body):
        kind = event.get("type")
        if kind == "content_block_start" and (event.get("content_block") or {}).get("type") == "tool_use":
            blocks[event["index"]] = {"name": event["content_block"].get("name"), "json": []}
        elif kind == "content_block_delta" and event.get("index") in blocks:
            delta = event.get("delta") or {}
            if delta.get("type") == "input_json_delta":
                blocks[event["index"]]["json"].append(delta.get("partial_json", ""))
    uses = []
    for index in sorted(blocks):
        raw = "".join(blocks[index]["json"])
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = raw
        uses.append({"name": blocks[index]["name"], "input": parsed})
    return uses


def read_capture(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def model_calls(records: list[dict]) -> list[ModelCall]:
    calls = []
    for record in records:
        if not is_model_call(record):
            continue
        body = record.get("request_body")
        responded, usage = response_usage(record.get("response_body"))
        calls.append(ModelCall(
            seq=record["seq"],
            host=record["host"],
            path=record["path"],
            status=record.get("status"),
            requested_model=body.get("model") if isinstance(body, dict) else None,
            responded_model=responded,
            usage=usage,
            tool_uses=response_tool_uses(record.get("response_body")),
            request_text=body if isinstance(body, str) else json.dumps(body),
            error=record.get("error"),
        ))
    return calls


def usage_totals(calls: list[ModelCall]) -> dict[str, int]:
    totals = {k: 0 for k in USAGE_FIELDS}
    for call in calls:
        for k in USAGE_FIELDS:
            totals[k] += call.usage.get(k, 0)
    totals["total_tokens"] = sum(totals[k] for k in USAGE_FIELDS)
    return totals
