import json
from pathlib import Path

import pytest

from pennybench.audit import audit_run
from pennybench.wire import model_calls, response_usage, usage_totals

SSE = "\n".join([
    "event: message_start",
    'data: {"type":"message_start","message":{"model":"claude-haiku-5-5","usage":'
    '{"input_tokens":5,"cache_creation_input_tokens":100,"cache_read_input_tokens":900,'
    '"output_tokens":1}}}',
    "event: content_block_delta",
    'data: {"type":"content_block_delta","delta":{"text":"hi"}}',
    "event: message_delta",
    'data: {"type":"message_delta","usage":{"output_tokens":42}}',
])


def wire_record(seq, host, body, response=SSE, path="/v1/messages?beta=true", **extra):
    return {"seq": seq, "method": "POST", "host": host, "path": path, "status": 200,
            "request_body": body, "response_body": response, **extra}


# Wire parsing

def test_streamed_usage_takes_final_output_count():
    model, usage = response_usage(SSE)
    assert model == "claude-haiku-5-5"
    assert usage == {"input_tokens": 5, "cache_creation_input_tokens": 100,
                     "cache_read_input_tokens": 900, "output_tokens": 42}


def test_json_usage_and_non_model_paths():
    records = [
        wire_record(1, "api.anthropic.com", {"model": "m"},
                    response={"model": "m", "usage": {"input_tokens": 3, "output_tokens": 4}}),
        wire_record(2, "api.anthropic.com", {}, path="/api/event_logging/v2/batch"),
        wire_record(3, "api.anthropic.com", {}, path="/v1/messages/count_tokens"),
    ]
    calls = model_calls(records)
    assert [c.seq for c in calls] == [1]
    assert usage_totals(calls)["total_tokens"] == 7


# Audit

ARM = {"harness_version": "2.1.302", "model": "claude-haiku-5-5", "adoption_marker": None}


def make_run(tmp_path: Path, trials: list[dict], *, treatment_marker=None,
             exclude=(), endpoint="http://host.docker.internal:8400") -> Path:
    plan = [{"trial_id": t["trial_id"], "role": t["role"], "task": t["task"], "rep": 0}
            for t in trials]
    manifest = {
        "arms": {
            "baseline": {**ARM},
            "treatment": {**ARM, "adoption_marker": treatment_marker,
                          "endpoint": {"base_url": endpoint}},
        },
        "plan": plan,
        "exclude": [{"task": t, "reason": "x"} for t in exclude],
        "host_home": "/Users/someone",
    }
    (tmp_path / "run.json").write_text(json.dumps(manifest))
    for t in trials:
        d = tmp_path / "trials" / t["trial_id"]
        (d / "wire").mkdir(parents=True)
        (d / "trial.json").write_text(json.dumps({
            "trial_id": t["trial_id"], "role": t["role"], "task": t["task"], "rep": 0,
            "status": t.get("status", "complete"), "agent_version": t.get("version", "2.1.302"),
        }))
        lines = [json.dumps(r) for r in t.get("wire", [])]
        (d / "wire" / "wire.jsonl").write_text("\n".join(lines) + "\n" if lines else "")
    return tmp_path


def pair(task="t1", base_host="api.anthropic.com", treat_host="host.docker.internal",
         base_text="plain", treat_text="plain", **overrides):
    base = {"trial_id": f"0-{task}-baseline", "role": "baseline", "task": task,
            "wire": [wire_record(1, base_host, {"model": "claude-haiku-5-5", "s": base_text})]}
    treat = {"trial_id": f"0-{task}-treatment", "role": "treatment", "task": task,
             "wire": [wire_record(1, treat_host, {"model": "claude-haiku-5-5", "s": treat_text})]}
    for key, value in overrides.items():
        role, field = key.split("__")
        (base if role == "baseline" else treat)[field] = value
    return [base, treat]


def failed(checks):
    return {c.name: c.failures for c in checks if not c.passed}


def test_clean_run_passes(tmp_path):
    run = make_run(tmp_path, pair(treat_text="RULES v1"), treatment_marker="RULES v1")
    assert failed(audit_run(run)) == {}


def test_native_arm_reaching_the_proxy_fails_route(tmp_path):
    run = make_run(tmp_path, pair(base_host="host.docker.internal"))
    assert "route" in failed(audit_run(run))


def test_marker_missing_from_treatment_fails_adoption(tmp_path):
    run = make_run(tmp_path, pair(), treatment_marker="RULES v1")
    assert any("absent" in f for f in failed(audit_run(run))["adoption"])


def test_marker_in_baseline_is_contamination(tmp_path):
    run = make_run(tmp_path, pair(base_text="RULES v1", treat_text="RULES v1"),
                   treatment_marker="RULES v1")
    assert any("contamination" in f for f in failed(audit_run(run))["adoption"])


def test_wrong_agent_version_fails_pins(tmp_path):
    run = make_run(tmp_path, pair(treatment__version="2.1.999"))
    assert "pins" in failed(audit_run(run))


def test_host_home_in_request_fails_isolation(tmp_path):
    run = make_run(tmp_path, pair(base_text="read /Users/someone/.claude/CLAUDE.md"))
    assert "isolation" in failed(audit_run(run))


def test_completed_trial_without_capture_fails(tmp_path):
    run = make_run(tmp_path, pair(treatment__wire=[]))
    assert "capture" in failed(audit_run(run))


def test_unfinished_pair_fails_complete_and_pairing(tmp_path):
    run = make_run(tmp_path, pair(treatment__status="harbor_failed"))
    result = failed(audit_run(run))
    assert "complete" in result and "pairing" in result


@pytest.mark.parametrize("status", ["agent_error"])
def test_agent_error_pairs_are_final_but_not_capture_failures(tmp_path, status):
    run = make_run(tmp_path, pair(treatment__status=status, treatment__wire=[]))
    assert failed(audit_run(run)) == {}
