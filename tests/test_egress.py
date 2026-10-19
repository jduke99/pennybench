import json
from pathlib import Path

import pytest

from pennybench.audit import audit_run
from pennybench.metrics import call_cost, run_metrics, unattributed_egress
from pennybench.wire import model_calls

SSE = ('data: {"type":"message_start","message":{"model":"claude-sonnet-5-5","usage":'
       '{"input_tokens":5,"cache_read_input_tokens":1000,"cache_creation_input_tokens":0,'
       '"output_tokens":1}}}\ndata: {"type":"message_delta","usage":{"output_tokens":%d}}')


def call(seq, host, text, out=10):
    return {"seq": seq, "method": "POST", "host": host, "path": "/v1/messages", "status": 200,
            "request_body": {"model": "claude-sonnet-5-5", "s": text}, "response_body": SSE % out}


def make_run(tmp_path: Path, egress: list[dict] | None):
    arms = {"baseline": {"harness_version": "2.1.302", "model": "claude-sonnet-5-5"},
            "treatment": {"harness_version": "2.1.302", "model": "claude-sonnet-5-5",
                          "endpoint": {"base_url": "http://host.docker.internal:8400"}}}
    trials = [("0-t1-baseline", "baseline", "api.anthropic.com", "n-base"),
              ("0-t1-treatment", "treatment", "host.docker.internal", "n-treat")]
    manifest = {"arms": arms, "plan": [{"trial_id": t, "role": r, "task": "t1", "rep": 0}
                                       for t, r, _, _ in trials],
                "exclude": [], "host_home": "/Users/x", "seed": 1, "stage": "smoke",
                "egress_capture": {"endpoint": "proxy", "port": 18999} if egress is not None else None}
    (tmp_path / "run.json").write_text(json.dumps(manifest))
    for trial_id, role, host, nonce in trials:
        d = tmp_path / "trials" / trial_id
        (d / "wire").mkdir(parents=True)
        (d / "trial.json").write_text(json.dumps({
            "trial_id": trial_id, "role": role, "task": "t1", "rep": 0, "status": "complete",
            "reward": 1.0, "agent_version": "2.1.302", "cache_nonce": nonce,
            "environment_sha256": "e", "task_skills": []}))
        (d / "wire" / "wire.jsonl").write_text(json.dumps(call(1, host, f"ref {nonce}")) + "\n")
    if egress is not None:
        (tmp_path / "egress").mkdir()
        (tmp_path / "egress" / "wire.jsonl").write_text("".join(json.dumps(r) + "\n" for r in egress))
    return tmp_path


def by_role(run):
    return {t["role"]: t["metrics"] for t in run_metrics(run)}


def test_overhead_is_upstream_cost_beyond_the_agents_own_calls(tmp_path):
    ping = call(2, "api.anthropic.com", "ref n-treat replay", out=1)
    run = make_run(tmp_path, [call(1, "api.anthropic.com", "ref n-treat"), ping,
                              call(3, "api.anthropic.com", "compaction prompt", out=50)])
    m = by_role(run)
    expected = call_cost(model_calls([ping])[0])
    assert m["treatment"]["gateway_overhead_cost"] == pytest.approx(expected)
    assert m["treatment"]["cost_all_in"] == pytest.approx(m["treatment"]["cost"] + expected)
    assert m["baseline"]["gateway_overhead_cost"] == 0.0
    loose = unattributed_egress(run)
    assert loose["calls"] == 1 and loose["cost"] > 0


def test_without_egress_capture_the_new_metrics_are_absent(tmp_path):
    m = by_role(make_run(tmp_path, None))
    assert m["treatment"]["gateway_overhead_cost"] is None and m["treatment"]["cost_all_in"] is None
    assert unattributed_egress(tmp_path) is None


def test_audit_requires_proxy_trials_in_the_upstream_capture(tmp_path):
    checks = {c.name: c for c in audit_run(make_run(tmp_path, [call(1, "api.anthropic.com", "other")]))}
    assert not checks["egress"].passed
    assert checks["egress"].failures == ["0-t1-treatment: proxy upstream capture is missing its calls"]
    ok = tmp_path / "ok"
    ok.mkdir()
    checks = {c.name: c for c in audit_run(make_run(ok, [call(1, "api.anthropic.com", "ref n-treat")]))}
    assert checks["egress"].passed


def test_egress_capture_requires_cache_isolation(tmp_path):
    from types import SimpleNamespace
    from pennybench.config import Endpoint
    from pennybench.run import RunError, start_egress_capture
    arm = SimpleNamespace(endpoint_name="proxy")
    experiment = SimpleNamespace(arms={"baseline": SimpleNamespace(endpoint_name=None),
                                       "treatment": arm}, cache_isolation="none")
    endpoint = Endpoint(name="proxy", base_url="http://x", egress_capture_port=18999)
    config = SimpleNamespace(endpoint=lambda name: endpoint, store=tmp_path)
    with pytest.raises(RunError, match="cache_isolation"):
        start_egress_capture(tmp_path, experiment, config)
