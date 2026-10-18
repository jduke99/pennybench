"""Reading a trial's wire capture: model calls and the usage each response reported."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

USAGE_FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                "output_tokens")


@dataclass(frozen=True)
class ModelCall:
    seq: int
    host: str
    path: str
    status: int | None
    requested_model: str | None
    responded_model: str | None
    usage: dict[str, int] = field(default_factory=dict)
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


def response_usage(body: object) -> tuple[str | None, dict[str, int]]:
    """Model and final usage from a Messages response, streamed (SSE text) or not (JSON).
    In a stream, message_start carries the input side and message_delta the final output
    count; later non-null values win."""
    if isinstance(body, dict):
        usage = body.get("usage") or {}
        return body.get("model"), {k: int(usage[k]) for k in USAGE_FIELDS if usage.get(k) is not None}
    if not isinstance(body, str):
        return None, {}
    model, usage = None, {}
    for event in _sse_events(body):
        if event.get("type") == "message_start":
            message = event.get("message") or {}
            model = message.get("model") or model
            source = message.get("usage") or {}
        elif event.get("type") == "message_delta":
            source = event.get("usage") or {}
        else:
            continue
        usage.update({k: int(source[k]) for k in USAGE_FIELDS if source.get(k) is not None})
    return model, usage


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
