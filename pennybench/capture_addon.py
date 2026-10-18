"""mitmproxy addon that records model-endpoint traffic for one trial.

Loaded by mitmdump, not imported by PennyBench. Every request to a capture host is written to
one JSONL file as it completes. Responses stream through unchanged: the addon tees chunks
instead of buffering, so the agent sees the same timing it would without capture.

Credentials are never written. Auth headers are replaced by their kind and a short hash, which
is enough for the audit to tell which credential a request carried.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time

from mitmproxy import ctx, http
from mitmproxy.net import encoding

AUTH_HEADERS = ("authorization", "x-api-key", "cookie", "proxy-authorization")


def _redact(name: str, value: str) -> str:
    digest = hashlib.sha256(value.encode()).hexdigest()[:12]
    if name == "authorization":
        scheme = value.split(" ", 1)[0] if " " in value else "?"
        token = value.split(" ", 1)[-1]
        return f"<{scheme} {token[:6]}… sha256:{digest}>"
    return f"<{value[:3]}… sha256:{digest}>"


def _headers(headers) -> dict[str, str]:
    return {
        k: _redact(k.lower(), v) if k.lower() in AUTH_HEADERS else v
        for k, v in headers.items()
    }


def _body(raw: bytes) -> object:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


class Capture:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = 0

    def load(self, loader) -> None:
        loader.add_option("pb_capture_file", str, "", "JSONL file for captured flows")
        loader.add_option("pb_capture_hosts", str, "", "comma-separated hosts to record")
        loader.add_option("pb_host_rewrites", str, "",
                          "comma-separated from=to upstream host rewrites")

    def _captured(self, flow: http.HTTPFlow) -> bool:
        host = flow.metadata.get("pb_original_host", flow.request.pretty_host)
        return host in {h for h in ctx.options.pb_capture_hosts.split(",") if h}

    def request(self, flow: http.HTTPFlow) -> None:
        flow.metadata["pb_original_host"] = flow.request.pretty_host
        flow.metadata["pb_started"] = time.time()
        rewrites = dict(r.split("=", 1) for r in ctx.options.pb_host_rewrites.split(",") if r)
        if flow.request.host in rewrites:
            flow.request.host = rewrites[flow.request.host]

    def responseheaders(self, flow: http.HTTPFlow) -> None:
        if not self._captured(flow):
            return
        chunks: list[bytes] = []
        flow.metadata["pb_chunks"] = chunks

        def tee(data: bytes) -> bytes:
            chunks.append(data)
            return data

        flow.response.stream = tee

    def response(self, flow: http.HTTPFlow) -> None:
        if self._captured(flow):
            self._write(flow, error=None)

    def error(self, flow: http.HTTPFlow) -> None:
        if self._captured(flow):
            self._write(flow, error=str(flow.error))

    def _write(self, flow: http.HTTPFlow, error: str | None) -> None:
        response = flow.response
        chunks = flow.metadata.get("pb_chunks")
        raw = b"".join(chunks) if chunks is not None else (response.content if response else b"")
        decode_error = None
        content_encoding = response.headers.get("content-encoding") if response else None
        if chunks is not None and content_encoding:
            # Streamed bodies arrive still content-encoded; decode for the record only.
            try:
                raw = encoding.decode(raw, content_encoding)
            except ValueError as exc:
                decode_error = f"{content_encoding}: {exc}"
        with self._lock:
            self._seq += 1
            record = {
                "seq": self._seq,
                "started_at": flow.metadata.get("pb_started"),
                "finished_at": time.time(),
                "method": flow.request.method,
                "scheme": flow.request.scheme,
                "host": flow.metadata.get("pb_original_host"),
                "port": flow.request.port,
                "path": flow.request.path,
                "request_headers": _headers(flow.request.headers),
                "request_body": _body(flow.request.content or b""),
                "status": response.status_code if response else None,
                "response_headers": _headers(response.headers) if response else None,
                "response_body": _body(raw),
                "error": error,
                "decode_error": decode_error,
            }
            with open(ctx.options.pb_capture_file, "a") as out:
                out.write(json.dumps(record) + "\n")


addons = [Capture()]
