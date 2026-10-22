"""One-shot model calls on the caller's Claude subscription, through headless Claude Code.

Offline studies need plain completions, not agent sessions: the caller's system prompt, no
tools, no settings or MCP servers. The proxy route in the environment is stripped so the call
runs on the signed-in subscription directly. Replies are cached by their full input, so a rerun
of a study resumes instead of repeating calls.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

PROXY_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_API_KEY")


class CallError(RuntimeError):
    pass


def complete(model: str, system: str, prompt: str, *, cache_dir: Path, max_out: int,
             schema: str | None = None) -> dict:
    """Return {result, structured, usage, cost_usd}. Claude Code fails a reply that reaches
    `max_out` rather than truncating it, so set it above the longest reply you expect."""
    key = hashlib.sha256(json.dumps([model, system, prompt, schema, max_out]).encode()).hexdigest()
    cache = cache_dir / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    env = {k: v for k, v in os.environ.items() if k not in PROXY_ENV}
    env |= {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(max_out), "MAX_THINKING_TOKENS": "0"}
    argv = ["claude", "-p", "--model", model, "--system-prompt", system, "--tools", "", "--strict-mcp-config",
            "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence", "--output-format", "json"]
    if schema:
        argv += ["--json-schema", schema]
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = subprocess.run(argv, input=prompt, capture_output=True, text=True, env=env, cwd=cache_dir, timeout=600)
    try:
        reply = json.loads(out.stdout)
    except ValueError:
        raise CallError(f"no JSON reply (exit {out.returncode}): {out.stderr[-500:]}") from None
    if reply.get("is_error"):
        raise CallError(f"model call failed: {reply.get('result')}")
    record = {"result": reply.get("result"), "structured": reply.get("structured_output"),
              "usage": reply.get("usage"), "cost_usd": reply.get("total_cost_usd")}
    cache.write_text(json.dumps(record))
    return record
