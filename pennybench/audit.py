"""The audit gate: checks that read only a run's sealed artifacts.

Every check states what it looked at and what it found. Stats refuse to run on a run whose
audit has any failure.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from pennybench.capture import ANTHROPIC_HOST
from pennybench.wire import model_calls, read_capture

FINAL_STATUSES = ("complete", "agent_error")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    failures: list[str] = field(default_factory=list)


@dataclass
class TrialEvidence:
    trial_id: str
    role: str
    task: str
    rep: int
    status: str
    agent_version: str | None
    hosts: set[str]
    requested_models: set[str]
    n_model_calls: int
    marker_hits: int
    home_hits: int
    missing_skills: list[str]
    nonce_missing: bool
    login_plan: str | None
    environment_sha256: str | None
    environment_error: str | None
    decode_errors: int
    aborted_calls: int


def _expected_host(arm: dict) -> str:
    endpoint = arm.get("endpoint")
    return urlparse(endpoint["base_url"]).hostname if endpoint else ANTHROPIC_HOST


def trial_evidence(trial_dir: Path, record: dict, manifest: dict) -> TrialEvidence:
    records = read_capture(trial_dir / "wire" / "wire.jsonl")
    calls = model_calls(records)
    markers = [a.get("adoption_marker") for a in manifest["arms"].values() if a.get("adoption_marker")]
    home = manifest.get("host_home") or ""
    return TrialEvidence(
        trial_id=record["trial_id"],
        role=record["role"],
        task=record["task"],
        rep=record["rep"],
        status=record["status"],
        agent_version=record.get("agent_version"),
        hosts={c.host for c in calls},
        requested_models={c.requested_model for c in calls if c.requested_model},
        n_model_calls=len(calls),
        marker_hits=sum(1 for c in calls if any(m in c.request_text for m in markers)),
        home_hits=sum(1 for c in calls if home and home in c.request_text),
        # Claude Code lists installed skills by name in its requests.
        login_plan=(lambda l: f"{l.get('subscription')}/{l.get('rate_limit_tier')}" if l.get("subscription") else None)(record.get("login") or {}),
        nonce_missing=bool(record.get("cache_nonce")) and bool(calls) and not any(
            record["cache_nonce"] in c.request_text for c in calls),
        environment_sha256=record.get("environment_sha256"),
        environment_error=record.get("environment_error"),
        missing_skills=[name for name in record.get("task_skills") or []
                        if calls and not any(name in c.request_text for c in calls)],
        # A stream the client abandoned (e.g. after a stall) ends mid-body and cannot be
        # decoded; that is an event worth reporting, not a capture failure.
        decode_errors=sum(1 for r in records if r.get("decode_error") and not r.get("error")),
        aborted_calls=sum(1 for r in records if r.get("error")),
    )


def load_evidence(run_dir: Path) -> tuple[dict, list[TrialEvidence]]:
    manifest = json.loads((run_dir / "run.json").read_text())
    evidence = []
    for path in sorted((run_dir / "trials").glob("*/trial.json")):
        record = json.loads(path.read_text())
        evidence.append(trial_evidence(path.parent, record, manifest))
    return manifest, evidence


def _check(name: str, failures: list[str], detail: str) -> Check:
    return Check(name=name, passed=not failures, detail=detail, failures=failures)


def audit_run(run_dir: Path, partial: bool = False) -> list[Check]:
    """With `partial`, a run stopped before its plan finished may pass `complete`; every
    other check still applies, and pairing still requires both arms of each finished pair."""
    manifest, evidence = load_evidence(run_dir)
    arms = manifest["arms"]
    planned = {t["trial_id"] for t in manifest["plan"]}
    final = [e for e in evidence if e.status in FINAL_STATUSES]
    checks = []

    missing = sorted(planned - {e.trial_id for e in final})
    checks.append(_check("complete", [] if partial else missing,
                         f"{len(final)} of {len(planned)} planned trials finished"
                         + (" (partial run accepted)" if partial and missing else "")))

    checks.append(_check(
        "capture",
        [f"{e.trial_id}: no model calls captured" for e in final
         if e.status == "complete" and e.n_model_calls == 0]
        + [f"{e.trial_id}: {e.decode_errors} undecodable bodies" for e in final if e.decode_errors],
        "every completed trial has decodable model calls on the wire"
        + "".join(f"; {e.trial_id}: {e.aborted_calls} call(s) aborted by the client"
                  for e in final if e.aborted_calls)))

    route_fail = []
    for e in final:
        expected = _expected_host(arms[e.role])
        if e.hosts - {expected}:
            route_fail.append(f"{e.trial_id}: expected {expected}, saw {sorted(e.hosts)}")
    checks.append(_check("route", route_fail,
                         "every model call went to the host its arm declares"))

    pin_fail = []
    for e in final:
        arm = arms[e.role]
        if e.agent_version and e.agent_version != arm["harness_version"]:
            pin_fail.append(f"{e.trial_id}: agent {e.agent_version} != {arm['harness_version']}")
        # Claude Code also calls a small model for titles and summaries, so the check is that
        # the arm's model appears, not that it is the only one.
        if e.n_model_calls and arm["model"] not in e.requested_models:
            pin_fail.append(f"{e.trial_id}: {arm['model']} never requested")
    checks.append(_check("pins", pin_fail, "harness version and model match the arm specs"))

    adoption_fail = []
    for role in arms:
        marker = arms[role].get("adoption_marker")
        if not marker:
            continue
        for e in final:
            if e.role == role and e.n_model_calls and e.marker_hits == 0:
                adoption_fail.append(f"{e.trial_id}: own marker {marker!r} absent")
            if e.role != role and e.marker_hits:
                adoption_fail.append(f"{e.trial_id}: other arm's marker present (contamination)")
    has_marker = any(a.get("adoption_marker") for a in arms.values())
    checks.append(_check(
        "adoption", adoption_fail,
        "treatment marker in every treatment trial, absent from every baseline"
        if has_marker else "no adoption marker declared; adoption not checked"))

    checks.append(_check(
        "task_skills",
        [f"{e.trial_id}: skills never seen by the model: {e.missing_skills}"
         for e in final if e.missing_skills],
        f"task skills {manifest.get('task_skills', 'without')}: every installed task skill "
        "appears in the trial's requests"))

    checks.append(_check(
        "cache_isolation",
        [f"{e.trial_id}: its cache isolation line never reached the model"
         for e in final if e.nonce_missing],
        f"cache isolation {manifest.get('cache_isolation', 'none')}: every trial's own "
        "reference line appears in its requests"))

    if manifest.get("egress_capture"):
        from pennybench.metrics import egress_calls_for, run_egress
        egress = run_egress(run_dir) or []
        egress_fail = []
        for e in final:
            if e.status != "complete" or not arms[e.role].get("endpoint"):
                continue
            record = json.loads((run_dir / "trials" / e.trial_id / "trial.json").read_text())
            if len(egress_calls_for(record.get("cache_nonce"), egress)) < e.n_model_calls:
                egress_fail.append(f"{e.trial_id}: proxy upstream capture is missing its calls")
        checks.append(_check("egress", egress_fail,
                             "every proxy trial's calls appear in the proxy's upstream capture"))

    plans: dict[tuple, set] = {}
    for e in final:
        if e.login_plan:
            plans.setdefault((e.task, e.rep), set()).add(e.login_plan)
    plan_fail = [f"{task} r{rep}: the arms of a pair used different account plans {sorted(p)}"
                 for (task, rep), p in plans.items() if len(p) > 1]
    run_plans = sorted({e.login_plan for e in final if e.login_plan})
    checks.append(_check("login_plan", plan_fail,
                         "both arms of every pair ran on one account plan"
                         + (f" (plans in this run: {', '.join(run_plans)})" if run_plans else "")))

    env_fail = [f"{e.trial_id}: package list not recorded ({e.environment_error})"
                for e in final if e.status == "complete" and not e.environment_sha256]
    for (task, rep), roles in by_pair_env(final).items():
        if len(set(roles.values())) > 1:
            env_fail.append(f"{task} r{rep}: arms ran on different package lists")
    checks.append(_check("environment", env_fail,
                         "every completed trial recorded its packages; both arms of a pair match"))

    checks.append(_check(
        "isolation",
        [f"{e.trial_id}: host home path in {e.home_hits} requests" for e in final if e.home_hits],
        "no host home-directory path appears in any request"))

    excluded = [x["task"] for x in manifest.get("exclude", [])]
    sym_fail = [f"pair {e.task} r{e.rep}: excluded task was run" for e in final if e.task in excluded]
    by_pair: dict[tuple, set] = {}
    for e in final:
        by_pair.setdefault((e.task, e.rep), set()).add(e.role)
    sym_fail += [f"{t} r{r}: only {sorted(roles)} finished" for (t, r), roles in by_pair.items()
                 if roles != set(arms)]
    checks.append(_check("pairing", sym_fail,
                         "every finished pair has both arms (a single-arm run has one trial per "
                         "task run); excluded tasks never ran"))
    return checks


def by_pair_env(evidence: list[TrialEvidence]) -> dict[tuple, dict[str, str]]:
    pairs: dict[tuple, dict[str, str]] = {}
    for e in evidence:
        if e.environment_sha256:
            pairs.setdefault((e.task, e.rep), {})[e.role] = e.environment_sha256
    return pairs


def write_audit(run_dir: Path, partial: bool = False) -> tuple[bool, Path]:
    checks = audit_run(run_dir, partial)
    passed = all(c.passed for c in checks)
    path = run_dir / "audit.json"
    path.write_text(json.dumps({"passed": passed, "partial": partial,
                                "checks": [asdict(c) for c in checks]},
                               indent=2) + "\n")
    return passed, path
