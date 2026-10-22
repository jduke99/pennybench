"""Offline replay of tau3 banking KB_search results through candidate tool-output reducers.

The proxy arm of `proxy-tau3-n50` scored 1/18 on banking_knowledge against 7/18 native. Every
KB_search result there was 12-26K chars, over the gateway's 8000-char floor for MCP output, so
the gateway replaced each with a generic 256-token Haiku digest. This script replays every such
result from the captured transcripts through:

  digest     the gateway's prompt and cap, on the model the local gateway uses (Haiku 5.5)
  select     Haiku picks document IDs given the search query and the user's latest message;
             the kept documents are copied verbatim from the result, the rest listed by ID
  select+g   select, plus every document naming a tool is kept regardless of Haiku's choice
  top2       the first two BM25 results verbatim, no model
  head_tail  the gateway's deterministic 3000+2000-char truncation, no model

and scores what survives against each task's grading config: the discoverable tool names and
argument values in `expected_actions`, and the `required_documents` IDs. Only gold items that
appear in a result count for that result. Model calls run on the caller's Claude subscription
through headless Claude Code and are cached, so a rerun resumes.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "runs/proxy-tau3-n50/20261021T170151Z-64a92a48"
SOURCE = ROOT / "runs/tau3-prep/source"
OUT = ROOT / "runs/tau3-kb-replay"
MODEL = "claude-haiku-5-5"
ABSTRACT_MIN_CHARS = 8000  # penny-router tool_output_abstract_min_chars
DIGEST_MAX_TOKENS = 256  # penny-router tool_output_digest_max_tokens
TOOL_NAME = "mcp__tau3-runtime__KB_search"
OMITTED = "\n\nNot shown: "

# Verbatim from penny-router apps/gateway/pennyrouter/tool_output_handler.py.
DIGEST_PROMPT = (
    "You are compressing fetched reference material (from {tool}: a web page or document) "
    "that an engineering agent pulled while working. Extract only what the agent could act "
    "on: facts, numbers, names, API signatures, quoted instructions — verbatim, never "
    "paraphrased into new claims.\n\n"
    "Structure: one line stating what this document is; then the extracted specifics; then "
    "one line noting what large sections were omitted (e.g. 'omitted: changelog, marketing "
    "copy'). If the content doesn't match a fetched document or you cannot tell what it is, "
    "say exactly that and quote its opening lines verbatim — never guess at its nature or "
    "invent an outcome. Plain text, no JSON."
)

SELECT_PROMPT = (
    "You choose which knowledge-base documents a customer-service agent needs to read. You "
    "get the agent's search query, the customer's latest message, and numbered search "
    "results. Return the IDs of every document the agent could need to answer the customer "
    "or take the action they want: product details, eligibility, fees, procedures, and any "
    "document that names a tool to use. When unsure, keep the document; drop only documents "
    "clearly about something else. Copy IDs exactly as written."
)
SELECT_SCHEMA = json.dumps({"type": "object", "required": ["keep"], "properties": {
    "keep": {"type": "array", "items": {"type": "string"}}}})

DOC = re.compile(r"(?m)^(\d+)\. (.+)\n   ID: (\S+)\n   Score: [\d.]+\n   Content: ")
TOOLISH = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+_\d{4}\b|`[a-z]+(?:_[a-z0-9]+)+\(|Tool: [a-z]")


def _text(content) -> str:
    return content if isinstance(content, str) else "".join(c.get("text", "") for c in content)


def _unwrap(raw: str) -> str:
    try:
        return json.loads(raw)["result"]
    except (ValueError, KeyError, TypeError):
        return raw


def gold_for(task: str) -> dict:
    config = json.loads((SOURCE / f"tau3-bench__tau3-banking_knowledge-task-{task}/tests/config.json").read_text())
    tools, values = set(), set()
    for action in config["expected_actions"]:
        args = action["arguments"]
        name = args.get("agent_tool_name") or args.get("discoverable_tool_name")
        if not name:
            continue
        tools.add(name)
        inner = args.get("arguments")
        inner = json.loads(inner) if isinstance(inner, str) and inner.strip() else inner or {}
        values.update(str(v) for v in inner.values() if isinstance(v, str) and len(v) > 3)
    return {"tools": tools, "values": values, "docs": set(config["task"]["required_documents"])}


def events():
    """Every KB_search result over the digest floor, with the context the gateway could see."""
    for trial in sorted(RUN.glob("trials/*banking_knowledge*")):
        meta = json.loads((trial / "trial.json").read_text())
        transcript = next(trial.glob("harbor/*/*/agent/claude-code.txt"))
        task = meta["task"].rsplit("-", 1)[1]
        calls, user = {}, ""
        for line in transcript.read_text().splitlines():
            try:
                message = json.loads(line)
            except ValueError:
                continue
            content = message.get("message", {}).get("content") if message.get("type") in ("assistant", "user") else None
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_use":
                    calls[block["id"]] = (block["name"].split("__")[-1], block["input"])
                elif block.get("type") == "tool_result" and block["tool_use_id"] in calls:
                    name, inp = calls[block["tool_use_id"]]
                    text = _text(block["content"])
                    if name in ("start_conversation", "send_message_to_user"):
                        user = _unwrap(text)
                    elif name == "KB_search" and len(text) > ABSTRACT_MIN_CHARS:
                        yield {"trial": meta["trial_id"], "role": meta["role"], "reward": meta["reward"],
                               "task": task, "query": inp.get("query", ""), "user": user, "raw": text}


def split_docs(result: str) -> list[dict]:
    heads = list(DOC.finditer(result))
    return [{"id": m.group(3), "title": m.group(2), "text": result[m.start():(heads[i + 1].start() if i + 1 < len(heads) else len(result))]}
            for i, m in enumerate(heads)]


def haiku(system: str, prompt: str, *, schema: str | None = None, max_out: int) -> dict:
    key = hashlib.sha256(json.dumps([MODEL, system, prompt, schema, max_out]).encode()).hexdigest()
    cache = OUT / "calls" / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    # Strip the proxy route so the call runs on the signed-in subscription directly.
    env = {k: v for k, v in os.environ.items() if k not in (
        "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_API_KEY")}
    env |= {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(max_out), "MAX_THINKING_TOKENS": "0"}
    argv = ["claude", "-p", "--model", MODEL, "--system-prompt", system, "--tools", "", "--strict-mcp-config",
            "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence", "--output-format", "json"]
    if schema:
        argv += ["--json-schema", schema]
    out = subprocess.run(argv, input=prompt, capture_output=True, text=True, env=env, cwd=OUT, timeout=300)
    reply = json.loads(out.stdout)
    if reply.get("is_error"):
        raise RuntimeError(f"model call failed: {reply.get('result')}")
    record = {"result": reply.get("result"), "structured": reply.get("structured_output"),
              "usage": reply.get("usage"), "cost_usd": reply.get("total_cost_usd")}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(record))
    return record


def envelope(query: str, docs: list[dict], keep: set[str], n_chars: int) -> str:
    shown = [d for d in docs if d["id"] in keep]
    omitted = "; ".join(f"{d['id']} ({d['title']})" for d in docs if d["id"] not in keep)
    return (f"[large-result] KB_search returned {len(docs)} documents ({n_chars} chars); showing the "
            f"{len(shown)} relevant to: \"{query}\". Shown documents are verbatim.\n\n"
            + "".join(d["text"] for d in shown) + (f"{OMITTED}{omitted}" if omitted else ""))


def reduce_all(event: dict) -> dict[str, str]:
    result = _unwrap(event["raw"])
    docs = split_docs(result)
    # Claude Code fails a reply that hits its output cap where the gateway's max_tokens=256 just
    # stops, so call uncapped and keep the share of the text that fits in 256 output tokens.
    reply = haiku(DIGEST_PROMPT.format(tool=TOOL_NAME), event["raw"][:40000], max_out=4096)
    spent = (reply["usage"] or {}).get("output_tokens") or 1
    digest = reply["result"][:len(reply["result"]) * DIGEST_MAX_TOKENS // max(spent, DIGEST_MAX_TOKENS)]
    picked = haiku(SELECT_PROMPT, f"Search query: {event['query']}\n\nCustomer's latest message:\n{event['user']}\n\n"
                   f"Search results:\n{result}", schema=SELECT_SCHEMA, max_out=2048)["structured"] or {}
    keep = set(picked.get("keep", [])) & {d["id"] for d in docs}
    guarded = keep | {d["id"] for d in docs if TOOLISH.search(d["text"])}
    return {"digest": digest,
            "select": envelope(event["query"], docs, keep, len(result)),
            "select+g": envelope(event["query"], docs, guarded, len(result)),
            "top2": envelope(event["query"], docs, {d["id"] for d in docs[:2]}, len(result)),
            "head_tail": f"{result[:3000]}\n[... {len(result) - 5000} of {len(result)} chars omitted ...]\n{result[-2000:]}",
            "full": result}


def score(event: dict, outputs: dict[str, str]) -> dict:
    result = _unwrap(event["raw"]).lower()
    gold = gold_for(event["task"])
    present = {kind: {g for g in gold[kind] if g.lower() in result} for kind in gold}
    rows = {}
    for arm, text in outputs.items():
        # The omitted-documents list names IDs and titles the model never read; it doesn't count.
        low = text.split(OMITTED)[0].lower()
        rows[arm] = {"chars": len(text)} | {
            kind: [sum(g.lower() in low for g in items), len(items)] for kind, items in present.items()}
    return rows


def report(scored: list[dict]) -> str:
    arms = list(scored[0]["arms"])
    full = sum(s["arms"]["full"]["chars"] for s in scored)
    lines = [f"# tau3 banking KB_search replay\n\n{len(scored)} KB_search results over {ABSTRACT_MIN_CHARS} chars, "
             f"from {len({s['trial'] for s in scored})} trials. Recall counts only gold items present in the "
             "original result.\n",
             "| Arm | Chars kept | Tool names | Arg values | Required docs (by ID) | Results keeping every tool+value |",
             "|---|---:|---:|---:|---:|---:|"]
    for arm in arms:
        tot = defaultdict(lambda: [0, 0])
        complete = eligible = chars = 0
        for s in scored:
            row = s["arms"][arm]
            chars += row["chars"]
            for kind in ("tools", "values", "docs"):
                tot[kind][0] += row[kind][0]; tot[kind][1] += row[kind][1]
            need = row["tools"][1] + row["values"][1]
            if need:
                eligible += 1
                complete += row["tools"][0] + row["values"][0] == need
        pct = lambda k: f"{tot[k][0]}/{tot[k][1]} ({100 * tot[k][0] / max(tot[k][1], 1):.0f}%)"
        lines.append(f"| {arm} | {100 * chars / full:.1f}% | {pct('tools')} | {pct('values')} | {pct('docs')} | "
                     f"{complete}/{eligible} |")
    lines.append("\nThe digest is plain text, so it rarely carries document IDs; its doc column undercounts the "
                 "facts it kept. Items named only in an envelope's omitted-documents list don't count as kept.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="replay only the first N results")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    found = list(events())[: args.limit]
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        outputs = list(pool.map(reduce_all, found))
    scored = []
    with (OUT / "results.jsonl").open("w") as f:
        for event, out in zip(found, outputs):
            row = {k: event[k] for k in ("trial", "role", "reward", "task", "query")} | {"arms": score(event, out)}
            f.write(json.dumps(row | {"outputs": {k: v for k, v in out.items() if k != "full"}}) + "\n")
            scored.append(row)
    text = report(scored)
    (OUT / "report.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
