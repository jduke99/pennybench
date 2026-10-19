import json
from pathlib import Path

import pytest
import yaml

from pennybench.audit import audit_run
from pennybench.plan import plan_trials
from pennybench.report import build_report, format_report
from pennybench.solo import solo_summary
from pennybench.spec import SpecError, load_experiment
from test_core import write_arm, write_experiment, write_tasks


def solo_experiment(tmp_path, **overrides):
    write_arm(tmp_path, "a", route="endpoint:proxy")
    write_tasks(tmp_path, ["t1", "t2"])
    path = write_experiment(tmp_path, ["a"], "route", **overrides)
    raw = yaml.safe_load(path.read_text())
    raw.pop("variable")
    path.write_text(yaml.safe_dump(raw))
    return load_experiment(path, tmp_path)


def test_single_arm_experiment_plans_one_trial_per_task_run(tmp_path):
    exp = solo_experiment(tmp_path, k=3)
    assert not exp.paired and exp.roles == ("solo",) and exp.variable is None
    trials = plan_trials(exp)
    assert len(trials) == 6 and {t.role for t in trials} == {"solo"}
    assert len({t.trial_id for t in trials}) == 6 and {t.position for t in trials} == {0}


def test_single_arm_rejects_a_variable_and_three_arms(tmp_path):
    write_arm(tmp_path, "a")
    write_tasks(tmp_path, ["t1"])
    with pytest.raises(SpecError, match="no variable"):
        load_experiment(write_experiment(tmp_path, ["a"], "route"), tmp_path)
    with pytest.raises(SpecError, match="arms must list"):
        load_experiment(write_experiment(tmp_path, ["a", "a", "a"], "route"), tmp_path)


def make_solo_run(tmp_path: Path, rewards: list[float | None], role="solo"):
    arms = {role: {"id": "a", "harness_version": "2.1.302", "model": "claude-sonnet-5-5"}}
    plan = [{"trial_id": f"{i}-t{i % 2}-r{i // 2}-{role}", "role": role, "task": f"t{i % 2}", "rep": i // 2}
            for i in range(len(rewards))]
    (tmp_path / "run.json").write_text(json.dumps({
        "experiment": "e", "stage": "smoke", "arms": arms, "plan": plan, "exclude": [],
        "host_home": "/Users/x", "seed": 1, "preregistered": False}))
    for spec, reward in zip(plan, rewards):
        d = tmp_path / "trials" / spec["trial_id"]
        (d / "wire").mkdir(parents=True)
        status = "complete" if reward is not None else "usage_limit"
        (d / "trial.json").write_text(json.dumps({
            **spec, "status": status, "reward": reward, "agent_version": "2.1.302",
            "environment_sha256": "e", "task_skills": []}))
        sse = ('data: {"type":"message_start","message":{"model":"claude-sonnet-5-5","usage":'
               '{"input_tokens":5,"cache_read_input_tokens":100,"cache_creation_input_tokens":50,'
               '"output_tokens":1}}}\ndata: {"type":"message_delta","usage":{"output_tokens":9}}')
        (d / "wire" / "wire.jsonl").write_text(json.dumps({
            "seq": 1, "method": "POST", "host": "api.anthropic.com", "path": "/v1/messages",
            "status": 200, "request_body": {"model": "claude-sonnet-5-5"}, "response_body": sse}) + "\n")
    return tmp_path


def test_single_arm_audit_needs_no_pair_and_report_is_never_a_claim(tmp_path):
    run = make_solo_run(tmp_path, [1.0, 0.0, 1.0, 1.0])
    assert all(c.passed for c in audit_run(run))
    report = build_report(run)
    text = format_report(report)
    assert "NOT A CLAIM" in text and "stats" not in report
    summary = report["solo"]["summary"]
    assert summary["n_trials"] == 4 and summary["mean_reward"] == pytest.approx(0.75)
    assert (run / "solo.json").exists()


def test_archived_attempts_do_not_override_finished_trials(tmp_path):
    import shutil
    from pennybench.metrics import run_metrics
    from pennybench.run import completed_trials
    run = make_solo_run(tmp_path, [1.0, 1.0])
    current = sorted((run / "trials").iterdir())[0]
    archived = current.with_name(current.name + ".attempt-1")
    shutil.copytree(current, archived)
    record = json.loads((archived / "trial.json").read_text())
    record["status"] = "usage_limit"
    record["reward"] = None
    (archived / "trial.json").write_text(json.dumps(record))
    metrics = run_metrics(run)
    assert len(metrics) == 2 and all(t["status"] == "complete" for t in metrics)
    assert len(completed_trials(run)) == 2
    checks = audit_run(run)
    assert all(c.passed for c in checks)
    assert next(c for c in checks if c.name == "complete").detail.startswith("2 of 2")


def test_incomplete_single_arm_trials_are_listed_and_excluded(tmp_path):
    run = make_solo_run(tmp_path, [1.0, None])
    summary = build_report(run, partial=True)["solo"]["summary"]
    assert summary["not_complete"] == {"usage_limit": 1} and summary["n_trials"] == 1


def test_reference_run_is_shown_beside_each_task(tmp_path):
    ref = make_solo_run(tmp_path / "ref", [1.0, 1.0], role="baseline") if (tmp_path / "ref").mkdir() is None else None
    run = make_solo_run(tmp_path / "run", [0.0, 1.0]) if (tmp_path / "run").mkdir() is None else None
    report = build_report(run, reference=ref)
    rows = report["solo"]["summary"]["tasks"]
    assert rows["t0"]["mean_reward"] == 0.0 and rows["t0"]["reference"]["mean_reward"] == 1.0
    assert "reference" in format_report(report)


def test_a_second_run_is_refused_while_one_is_active_but_a_stale_lock_is_ignored(tmp_path):
    import os
    from pennybench.run import RunError, acquire_run_lock
    first = acquire_run_lock(tmp_path, tmp_path / "run-a")
    with pytest.raises(RunError, match="another run is active"):
        acquire_run_lock(tmp_path, tmp_path / "run-b")
    first.write_text("999999999 " + str(tmp_path / "run-a"))
    assert acquire_run_lock(tmp_path, tmp_path / "run-b").read_text().startswith(str(os.getpid()))
