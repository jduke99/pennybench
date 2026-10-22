"""Does query-driven extraction of a large document keep what a reader needs? A general check.

The tau3 replay (benchmarks/tau3/kb_replay.py) tested reducers on one knowledge base whose
critical facts are tool names. This study uses 20 long Wikipedia articles (7K-30K tokens) and
questions with known answers instead, so nothing is tuned to that domain. Sonnet writes three
questions per article: a body fact, a paraphrased fact, and one combining two sections; every
answer must be an exact substring of the article. Each (article, question) is reduced by:

  digest      the gateway's generic digest prompt and 256-token cap; it never sees the question
  answer      Haiku answers the question with verbatim supporting quotes
  sections    Haiku picks the article's sections; code copies them verbatim
  paragraphs  Haiku picks paragraphs; code copies them verbatim under their heading
  head_tail   the gateway's deterministic 3000+2000-char truncation
  full        the whole article

Sonnet then answers the question from the reduced text alone, and Haiku grades that answer
against the reference facts. Model calls run on the caller's Claude subscription and are cached.
"""

import argparse
import concurrent.futures
import json
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from pennybench.headless import complete

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs/wiki-extract"
ARTICLES = OUT / "articles"
CALLS = OUT / "calls"
CHEAP, READER = "claude-haiku-5-5", "claude-sonnet-5-5"
DIGEST_MAX_TOKENS = 256  # penny-router tool_output_digest_max_tokens
DIGEST_MAX_INPUT = 40000  # penny-router tool_output_max_input_chars
OMITTED = "\n\nNot shown: "
TITLES = ["Apollo_11", "Great_Barrier_Reef", "Python_(programming_language)", "French_Revolution",
          "Photosynthesis", "Bitcoin", "Mount_Everest", "The_Beatles", "Amazon_River", "Marie_Curie",
          "Byzantine_Empire", "Linux", "Black_hole", "Coffee", "Tokyo", "Colosseum", "Antarctica", "Jazz",
          "International_Space_Station", "Penicillin"]

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
QUESTION_PROMPT = (
    "Write three questions someone might need answered from the article you are given, in this "
    "order: (1) a specific fact stated in the body, not the opening summary; (2) a specific fact "
    "asked in different words than the article uses; (3) a question whose answer combines two "
    "facts from different sections. For each, give `answers`: the shortest exact substrings of "
    "the article (copied character for character, 1-8 words each) that a correct answer must "
    "contain, two for question 3. Choose facts stated in only one place. Don't mention the "
    "article in the question."
)
QUESTION_SCHEMA = json.dumps({"type": "object", "required": ["questions"], "properties": {"questions": {
    "type": "array", "items": {"type": "object", "required": ["question", "answers"], "properties": {
        "question": {"type": "string"}, "answers": {"type": "array", "items": {"type": "string"}}}}}}})
ANSWER_PROMPT = (
    "Answer the question from the document you are given. Reply with the answer, then the exact "
    "sentences that support it, quoted verbatim. If the document doesn't contain the answer, say "
    "NOT FOUND."
)
PICK_PROMPT = (
    "An agent is reading a long document to answer a question. You get the question and the "
    "document split into labeled {unit}s. Return the labels of the {unit}s the agent needs to "
    "answer it, including any {unit} that holds a fact, qualifier or condition the answer depends "
    "on. Leave out everything else. Copy labels exactly as written."
)
PICK_SCHEMA = json.dumps({"type": "object", "required": ["keep"], "properties": {
    "keep": {"type": "array", "items": {"type": "string"}}}})
READER_PROMPT = (
    "Answer the user's question using only the tool output they give you, which comes from "
    "reading a document. Be brief: one or two sentences. If the output doesn't contain the "
    "answer, say you can't tell."
)
JUDGE_PROMPT = (
    "Grade whether a response answers a question correctly, given the reference facts. Correct "
    "means it states every reference fact; paraphrase and different number formats are fine. A "
    "refusal or \"can't tell\" is incorrect."
)
JUDGE_SCHEMA = json.dumps({"type": "object", "required": ["correct"], "properties": {"correct": {"type": "boolean"}}})
HEADING = re.compile(r"(?m)^(=+) (.+?) =+\s*$")
KINDS = ("body fact", "paraphrased", "two sections")


def fetch():
    """Download each article's plain text once. The files are untrusted data; only parsed."""
    ARTICLES.mkdir(parents=True, exist_ok=True)
    for title in TITLES:
        path = ARTICLES / f"{title}.json"
        if path.exists():
            continue
        query = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1,
                                        "exsectionformat": "wiki", "redirects": 1, "format": "json", "titles": title})
        req = urllib.request.Request(f"https://en.wikipedia.org/w/api.php?{query}",
                                     headers={"user-agent": "pennybench-wiki-extract/0.1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            path.write_bytes(r.read())


def load(title: str) -> dict:
    page = next(iter(json.loads((ARTICLES / f"{title}.json").read_text())["query"]["pages"].values()))
    return {"title": page["title"], "text": page["extract"].strip()}


def sections_of(text: str) -> list[dict]:
    """Sections with a non-empty body, each holding its paragraphs. The lead has no heading."""
    marks = list(HEADING.finditer(text))
    spans = [("", 0, marks[0].start() if marks else len(text))] + [
        (m.group(0).strip(), m.end(), marks[i + 1].start() if i + 1 < len(marks) else len(text))
        for i, m in enumerate(marks)]
    out = []
    for heading, start, end in spans:
        paras = [p.strip() for p in re.split(r"\n\s*\n", text[start:end]) if p.strip()]
        if paras:
            out.append({"label": f"S{len(out) + 1}", "heading": heading, "paras": paras})
    n = 0
    for s in out:
        s["plabels"] = [f"P{(n := n + 1)}" for _ in s["paras"]]
    return out


def section_view(secs: list[dict]) -> str:
    return "\n\n".join(f"[{s['label']}] {s['heading'] or '(lead)'}\n" + "\n\n".join(s["paras"]) for s in secs)


def paragraph_view(secs: list[dict]) -> str:
    return "\n\n".join((s["heading"] or "(lead)") + "\n" + "\n\n".join(
        f"[{l}] {p}" for l, p in zip(s["plabels"], s["paras"])) for s in secs)


def envelope(article: dict, question: str, secs: list[dict], keep: set[str], unit: str) -> str:
    shown, omitted = [], []
    for s in secs:
        paras = s["paras"] if s["label"] in keep else [p for l, p in zip(s["plabels"], s["paras"]) if l in keep]
        if paras:
            shown.append("\n\n".join(([s["heading"]] if s["heading"] else []) + paras))
        if len(paras) < len(s["paras"]):
            name = s["heading"].strip("= ") or "lead"
            omitted.append(name if not paras else f"{name} ({len(s['paras']) - len(paras)} of {len(s['paras'])} paragraphs)")
    return (f"[large-file] {article['title']}: {len(article['text'])} chars; showing the {unit}s relevant to: "
            f"\"{question}\". Shown text is verbatim.\n\n" + "\n\n".join(shown)
            + (f"{OMITTED}{'; '.join(omitted)}" if omitted else ""))


def questions_for(title: str) -> list[dict]:
    article = load(title)
    reply = complete(READER, QUESTION_PROMPT, f"Article: {article['title']}\n\n{article['text']}",
                     cache_dir=CALLS, max_out=2048, schema=QUESTION_SCHEMA)
    found = (reply["structured"] or {}).get("questions", [])[:3]
    return [{"title": title, "kind": KINDS[i], "question": q["question"], "answers": q["answers"]}
            for i, q in enumerate(found) if q["answers"] and all(a in article["text"] for a in q["answers"])]


def reduce_all(q: dict) -> dict[str, str]:
    article = load(q["title"])
    text, secs = article["text"], sections_of(article["text"])
    # Claude Code fails a reply that hits its output cap where the gateway's max_tokens just stops,
    # so call uncapped and keep the share of the text that fits in the gateway's 256 tokens.
    reply = complete(CHEAP, DIGEST_PROMPT.format(tool="WebFetch"), text[:DIGEST_MAX_INPUT], cache_dir=CALLS, max_out=4096)
    spent = (reply["usage"] or {}).get("output_tokens") or 1
    digest = reply["result"][:len(reply["result"]) * DIGEST_MAX_TOKENS // max(spent, DIGEST_MAX_TOKENS)]
    answer = complete(CHEAP, ANSWER_PROMPT, f"Question: {q['question']}\n\nDocument: {article['title']}\n\n{text}",
                      cache_dir=CALLS, max_out=2048)["result"]
    picks = {}
    for unit, view in (("section", section_view), ("paragraph", paragraph_view)):
        reply = complete(CHEAP, PICK_PROMPT.format(unit=unit), f"Question: {q['question']}\n\n{view(secs)}",
                         cache_dir=CALLS, max_out=2048, schema=PICK_SCHEMA)
        picks[unit] = set((reply["structured"] or {}).get("keep", []))
    return {"digest": digest, "answer": answer,
            "sections": envelope(article, q["question"], secs, picks["section"], "section"),
            "paragraphs": envelope(article, q["question"], secs, picks["paragraph"], "paragraph"),
            "head_tail": f"{text[:3000]}\n[... {len(text) - 5000} of {len(text)} chars omitted ...]\n{text[-2000:]}",
            "full": text}


def read_and_grade(q: dict, arm: str, output: str) -> dict:
    title = load(q["title"])["title"]
    reply = complete(READER, READER_PROMPT, f"Question: {q['question']}\n\nResult of reading {title}:\n\n{output}",
                     cache_dir=CALLS, max_out=1024)
    verdict = complete(CHEAP, JUDGE_PROMPT, f"Question: {q['question']}\nReference facts: {json.dumps(q['answers'])}\n"
                       f"Response: {reply['result']}", cache_dir=CALLS, max_out=512, schema=JUDGE_SCHEMA)
    usage = reply["usage"] or {}
    shown = output.split(OMITTED)[0].lower()
    return {"arm": arm, "title": q["title"], "chars": len(output), "full_chars": len(load(q["title"])["text"]),
            "retained": all(a.lower() in shown for a in q["answers"]),
            "correct": bool((verdict["structured"] or {}).get("correct")), "response": reply["result"],
            "reader_input_tokens": sum(usage.get(k) or 0 for k in (
                "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))}


def report(rows: list[dict], n_questions: int) -> str:
    by_arm = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    lines = [f"# Wikipedia extraction replay\n\n{n_questions} questions over {len({r["title"] for r in rows})} articles. Sonnet 5.5 "
             "answers from each arm's output alone; Haiku 5.5 grades against the reference facts.\n",
             "| Arm | Chars kept | Sonnet input tokens (mean) | Answer text retained | Sonnet correct | "
             + " | ".join(f"Correct: {k}" for k in KINDS) + " |",
             "|---|---:|---:|---:|---:|" + "---:|" * len(KINDS)]
    for arm, rs in by_arm.items():
        pct = lambda xs, key: f"{sum(x[key] for x in xs)}/{len(xs)}" if xs else "-"
        kept = 100 * sum(r["chars"] for r in rs) / sum(r["full_chars"] for r in rs)
        lines.append(f"| {arm} | {kept:.1f}% | {sum(r['reader_input_tokens'] for r in rs) // len(rs):,} | "
                     f"{pct(rs, 'retained')} | {pct(rs, 'correct')} | "
                     + " | ".join(pct([r for r in rs if r["kind"] == k], "correct") for k in KINDS) + " |")
    lines.append("\nThe `answer` arm paraphrases, so its retained column undercounts; its correct column is the "
                 "comparable one. Sonnet input includes about 600 tokens of fixed headless-call overhead.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="use only the first N articles")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    fetch()
    titles = TITLES[: args.limit]
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        questions = [q for qs in pool.map(questions_for, titles) for q in qs]
        outputs = list(pool.map(reduce_all, questions))
        jobs = [(q, arm, text) for q, out in zip(questions, outputs) for arm, text in out.items()]
        graded = list(pool.map(lambda job: read_and_grade(*job), jobs))
    rows = [{"title": q["title"], "kind": q["kind"]} | g for (q, _, _), g in zip(jobs, graded)]
    with (OUT / "results.jsonl").open("w") as f:
        for q, out in zip(questions, outputs):
            f.write(json.dumps(q | {"outputs": {k: v for k, v in out.items() if k != "full"}}) + "\n")
    (OUT / "grades.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    text = report(rows, len(questions))
    (OUT / "report.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
