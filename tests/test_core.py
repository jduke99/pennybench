from pathlib import Path

import pytest
import yaml

from pennybench.agent_env import ENDPOINT_SECRET, UPSTREAM_SECRET, build_trial_env
from pennybench.config import ConfigError, load_local_config
from pennybench.plan import plan_trials
from pennybench.run import find_secret_leaks
from pennybench.spec import SpecError, load_arm, load_experiment

OAUTH = "sk-ant-oat01-test-secret"
PROXY_KEY = "pr-test-secret"

BASE_ARM = {
    "harness": "claude-code",
    "harness_version": "2.1.302",
    "model": "claude-haiku-5-5",
    "effort": None,
    "auth": "sub",
    "route": "native",
}


def write_arm(root: Path, arm_id: str, **overrides) -> Path:
    path = root / "arms" / f"{arm_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({**BASE_ARM, "id": arm_id, **overrides}))
    return path


def write_tasks(root: Path, names: list[str]) -> None:
    for name in names:
        (root / "tasks" / name).mkdir(parents=True)
        (root / "tasks" / name / "task.toml").write_text('schema_version = "1.4"\n')


def write_experiment(root: Path, arms: list[str], variable: str, **overrides) -> Path:
    path = root / "experiments" / "exp.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {"id": "exp", "arms": arms, "variable": variable, "tasks": "tasks",
           "stage": "smoke", "k": 1, "seed": 7, "task_skills": "without", **overrides}
    path.write_text(yaml.safe_dump(raw))
    return path


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "pennybench.local.toml"
    path.write_text(
        '[endpoints.proxy]\nbase_url = "http://host.docker.internal:8400"\n'
        'key_env = "PROXY_KEY"\nenv = { ENABLE_TOOL_SEARCH = "true" }\n'
        '[auth.sub]\nkind = "oauth"\ntoken_env = "OAUTH_TOKEN"\n'
        '[auth.api]\nkind = "api_key"\ntoken_env = "API_KEY"\n'
    )
    return load_local_config(path)


ENVIRON = {
    "PATH": "/usr/bin", "HOME": "/home/x",
    "OAUTH_TOKEN": OAUTH, "PROXY_KEY": PROXY_KEY, "API_KEY": "sk-ant-api-secret",
    # A caller running inside a proxied agent session carries these; none may leak.
    "ANTHROPIC_BASE_URL": "https://leaky.example", "ANTHROPIC_CUSTOM_HEADERS": "x-leak: 1",
    "CLAUDE_CODE_SESSION_ID": "abc",
}


# One-variable check

def test_route_experiment_with_one_difference_loads(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy")
    write_tasks(tmp_path, ["t1"])
    exp = load_experiment(write_experiment(tmp_path, ["a", "b"], "route"), tmp_path)
    assert exp.baseline.id == "a" and exp.treatment.route == "endpoint:proxy"


def test_extra_difference_is_rejected(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy", model="claude-sonnet-5-5")
    write_tasks(tmp_path, ["t1"])
    with pytest.raises(SpecError, match=r"differ in \['model'\]"):
        load_experiment(write_experiment(tmp_path, ["a", "b"], "route"), tmp_path)


def test_declared_variable_must_actually_differ(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b")
    write_tasks(tmp_path, ["t1"])
    with pytest.raises(SpecError, match="do not differ"):
        load_experiment(write_experiment(tmp_path, ["a", "b"], "route"), tmp_path)


def test_injected_file_content_counts_as_a_difference(tmp_path):
    (tmp_path / "r1.txt").write_text("rules v1")
    (tmp_path / "r2.txt").write_text("rules v2")
    write_arm(tmp_path, "a", inject={"append_system_prompt_file": "r1.txt"})
    write_arm(tmp_path, "b", inject={"append_system_prompt_file": "r2.txt"})
    write_tasks(tmp_path, ["t1"])
    exp = load_experiment(write_experiment(tmp_path, ["a", "b"], "inject"), tmp_path)
    assert exp.variable == "inject"
    with pytest.raises(SpecError, match="do not differ"):
        (tmp_path / "r2.txt").write_text("rules v1")
        load_experiment(write_experiment(tmp_path, ["a", "b"], "inject"), tmp_path)


def test_exclusions_need_reasons_and_known_tasks(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy")
    write_tasks(tmp_path, ["t1", "t2"])
    with pytest.raises(SpecError, match="reason"):
        load_experiment(write_experiment(tmp_path, ["a", "b"], "route",
                                         exclude=[{"task": "t1"}]), tmp_path)
    with pytest.raises(SpecError, match="unknown tasks"):
        load_experiment(write_experiment(tmp_path, ["a", "b"], "route",
                                         exclude=[{"task": "nope", "reason": "x"}]), tmp_path)
    exp = load_experiment(write_experiment(tmp_path, ["a", "b"], "route",
                                           exclude=[{"task": "t1", "reason": "x"}]), tmp_path)
    assert [p.name for p in exp.task_dirs()] == ["t2"]


def test_arm_id_must_match_file_name(tmp_path):
    path = write_arm(tmp_path, "a")
    path.rename(path.with_name("other.yaml"))
    with pytest.raises(SpecError, match="must match"):
        load_arm(path.with_name("other.yaml"))


# Trial environment

def test_native_oauth_arm_gets_only_the_subscription_token(tmp_path, config):
    arm = load_arm(write_arm(tmp_path, "a"))
    env = build_trial_env(arm, config, ENVIRON)
    assert env.agent_env == {"CLAUDE_CODE_OAUTH_TOKEN": f"${{{UPSTREAM_SECRET}}}"}
    assert env.host_env == {"PATH": "/usr/bin", "HOME": "/home/x", UPSTREAM_SECRET: OAUTH}
    assert env.secrets == (OAUTH,)


def test_proxy_oauth_arm_sends_both_credentials_by_reference(tmp_path, config):
    arm = load_arm(write_arm(tmp_path, "b", route="endpoint:proxy"))
    env = build_trial_env(arm, config, ENVIRON)
    assert env.agent_env == {
        "ANTHROPIC_BASE_URL": "http://host.docker.internal:8400",
        "ANTHROPIC_AUTH_TOKEN": f"${{{UPSTREAM_SECRET}}}",
        "ANTHROPIC_API_KEY": f"${{{ENDPOINT_SECRET}}}",
        "ENABLE_TOOL_SEARCH": "true",
    }
    assert env.host_env[ENDPOINT_SECRET] == PROXY_KEY
    assert set(env.secrets) == {OAUTH, PROXY_KEY}


def test_no_caller_session_variables_reach_harbor(tmp_path, config):
    for overrides in ({}, {"route": "endpoint:proxy"}):
        arm = load_arm(write_arm(tmp_path, "a", **overrides))
        env = build_trial_env(arm, config, ENVIRON)
        assert not any(k.startswith(("ANTHROPIC", "CLAUDE")) for k in env.host_env)
        assert all(OAUTH not in v and PROXY_KEY not in v for v in env.agent_env.values())


def test_missing_secret_fails_before_any_trial(tmp_path, config):
    arm = load_arm(write_arm(tmp_path, "b", route="endpoint:proxy"))
    with pytest.raises(ConfigError, match="PROXY_KEY"):
        build_trial_env(arm, config, {**ENVIRON, "PROXY_KEY": ""})


def test_api_key_profile_cannot_share_x_api_key_with_a_keyed_proxy(tmp_path, config):
    arm = load_arm(write_arm(tmp_path, "b", route="endpoint:proxy", auth="api"))
    with pytest.raises(ConfigError, match="collide"):
        build_trial_env(arm, config, ENVIRON)


def test_unknown_endpoint_is_a_config_error(tmp_path, config):
    arm = load_arm(write_arm(tmp_path, "b", route="endpoint:nowhere"))
    with pytest.raises(ConfigError, match="nowhere"):
        build_trial_env(arm, config, ENVIRON)


# Plan

def test_plan_alternates_arm_order_and_is_seeded(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy")
    write_tasks(tmp_path, ["t1", "t2", "t3", "t4"])
    exp = load_experiment(write_experiment(tmp_path, ["a", "b"], "route", k=2), tmp_path)
    trials = plan_trials(exp)
    assert len(trials) == 16
    firsts = [t.role for t in trials if t.position == 0]
    assert firsts == ["baseline", "treatment"] * 4
    assert {(t.task, t.rep) for t in trials} == {(f"t{i}", r) for i in range(1, 5) for r in (0, 1)}
    assert trials == plan_trials(exp)
    for pair in range(8):
        both = [t for t in trials if t.pair == pair]
        assert {t.role for t in both} == {"baseline", "treatment"}
        assert len({(t.task, t.rep) for t in both}) == 1


# Secret scan

def test_plan_orders_by_agent_limit_then_verifier_and_preserves_pairs(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy")
    limits = {"long": (1800, 900), "short": (600, 600), "tie": (600, 900)}
    write_tasks(tmp_path, list(limits))
    for name, (agent, verifier) in limits.items():
        (tmp_path / "tasks" / name / "task.toml").write_text(
            f'[agent]\ntimeout_sec = {agent}\n[verifier]\ntimeout_sec = {verifier}\n')
    exp = load_experiment(write_experiment(
        tmp_path, ["a", "b"], "route", k=2, task_order="agent_timeout"), tmp_path)
    trials = plan_trials(exp)
    assert [t.task for t in trials if t.position == 0] == ["short", "short", "tie", "tie", "long", "long"]
    assert [t.role for t in trials if t.position == 0] == ["baseline", "treatment"] * 3
    assert trials == plan_trials(exp)
    for pair in range(6):
        a, b = trials[2 * pair:2 * pair + 2]
        assert (a.task, a.rep) == (b.task, b.rep)


def test_pinned_local_task_tree_rejects_changes(tmp_path):
    from pennybench.digest import tree_sha256
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy")
    write_tasks(tmp_path, ["t1"])
    path = write_experiment(tmp_path, ["a", "b"], "route", tasks={
        "path": "tasks", "sha256": tree_sha256(tmp_path / "tasks")})
    assert len(load_experiment(path, tmp_path).task_dirs()) == 1
    (tmp_path / "tasks" / "t1" / "task.toml").write_text('[agent]\ntimeout_sec = 42\n')
    with pytest.raises(SpecError, match="task tree has content"):
        load_experiment(path, tmp_path)


def test_secret_scan_finds_leaks_and_passes_clean_trees(tmp_path):
    (tmp_path / "clean.json").write_text('{"ANTHROPIC_API_KEY": "${PENNYBENCH_SECRET_ENDPOINT}"}')
    assert find_secret_leaks(tmp_path, (OAUTH, PROXY_KEY)) == []
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "log.txt").write_text(f"token={OAUTH}")
    assert find_secret_leaks(tmp_path, (OAUTH, PROXY_KEY)) == ["sub/log.txt"]


# Injected directories, task samples, datasets

def test_injected_directory_is_hashed_by_content(tmp_path):
    for name, text in (("s1", "v1"), ("s2", "v2")):
        (tmp_path / name / "skill").mkdir(parents=True)
        (tmp_path / name / "skill" / "SKILL.md").write_text(text)
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", inject={"skills_dir": "s1/skill"})
    write_tasks(tmp_path, ["t1"])
    assert load_experiment(write_experiment(tmp_path, ["a", "b"], "inject"), tmp_path)
    write_arm(tmp_path, "a", inject={"skills_dir": "s2/skill"})
    assert load_experiment(write_experiment(tmp_path, ["a", "b"], "inject"), tmp_path)
    (tmp_path / "s2" / "skill" / "SKILL.md").write_text("v1")
    with pytest.raises(SpecError, match="do not differ"):
        load_experiment(write_experiment(tmp_path, ["a", "b"], "inject"), tmp_path)


def test_sample_is_seeded_stable_and_excludes_first(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy")
    write_tasks(tmp_path, [f"t{i}" for i in range(20)])
    exp = load_experiment(write_experiment(tmp_path, ["a", "b"], "route", sample=5), tmp_path)
    first = [p.name for p in exp.task_dirs()]
    k3 = load_experiment(write_experiment(tmp_path, ["a", "b"], "route", sample=5, k=3), tmp_path)
    assert len(first) == 5 and [p.name for p in k3.task_dirs()] == first
    excluded = load_experiment(write_experiment(
        tmp_path, ["a", "b"], "route", sample=5, exclude=[{"task": first[0], "reason": "x"}]),
        tmp_path)
    assert first[0] not in [p.name for p in excluded.task_dirs()]
    with pytest.raises(SpecError, match="exceeds"):
        load_experiment(write_experiment(tmp_path, ["a", "b"], "route", sample=50), tmp_path)


def test_dataset_must_be_pinned_and_match_its_hash(tmp_path):
    from pennybench.datasets import DatasetError, dataset_dir, ensure_dataset
    from pennybench.digest import tree_sha256
    with pytest.raises(DatasetError, match="fixed ref"):
        dataset_dir("org/name@latest", tmp_path)
    target = dataset_dir("org/name@v1", tmp_path)
    (target / "t1").mkdir(parents=True)
    (target / "t1" / "task.toml").write_text("x")
    assert ensure_dataset("org/name@v1", tree_sha256(target), tmp_path) == target
    with pytest.raises(DatasetError, match="expected"):
        ensure_dataset("org/name@v1", "0" * 64, tmp_path)


# Builder config and oracle verdicts

def test_docker_builder_config(tmp_path):
    path = tmp_path / "pennybench.local.toml"
    path.write_text('[docker]\nbuilder = "pb"\nbuild_cache_cap_gb = 40\n')
    config = load_local_config(path)
    assert config.builder.env() == {"BUILDX_BUILDER": "pb"}
    assert config.builder.cache_cap_gb == 40
    path.write_text("")
    assert load_local_config(path).builder is None
    path.write_text('[docker]\nbuilder = "pb"\nbuild_cache_cap_gb = 0\n')
    with pytest.raises(ConfigError, match="positive"):
        load_local_config(path)


def test_oracle_failure_rule():
    from pennybench.oracle import failed
    assert not failed({"status": "complete", "reward": 1.0})
    assert failed({"status": "complete", "reward": 0.5})
    assert failed({"status": "complete", "reward": None})
    assert failed({"status": "agent_error", "reward": 1.0})


# Task skills

def test_task_skills_setting_is_required_and_validated(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy")
    write_tasks(tmp_path, ["t1"])
    with pytest.raises(SpecError, match="task_skills"):
        load_experiment(write_experiment(tmp_path, ["a", "b"], "route", task_skills="maybe"),
                        tmp_path)


def test_task_skill_dirs_takes_only_folders_with_skill_md(tmp_path):
    from pennybench.spec import task_skill_dirs
    skills = tmp_path / "environment" / "skills"
    (skills / "real").mkdir(parents=True)
    (skills / "real" / "SKILL.md").write_text("x")
    (skills / "licenses").mkdir()
    (skills / "README.md").write_text("x")
    assert [p.name for p in task_skill_dirs(tmp_path)] == ["real"]
    assert task_skill_dirs(tmp_path / "nowhere") == []


def test_harbor_command_registers_each_task_skill(tmp_path, config):
    from pennybench.harbor import harbor_command
    arm = load_arm(write_arm(tmp_path, "a"))
    env = build_trial_env(arm, config, ENVIRON)
    argv = harbor_command(arm, tmp_path, tmp_path / "out", env, tmp_path, {}, [],
                          [tmp_path / "s1", tmp_path / "s2"])
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "--skill"] == [
        str(tmp_path / "s1"), str(tmp_path / "s2")]


# Environment manifests

def test_manifest_is_sorted_by_section(monkeypatch):
    import subprocess
    from pennybench import environment
    stdout = "# python\nzeta==1\nalpha==2\n# dpkg\nlibc=2.39\n# apk\n# npm-global\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout, ""))
    assert environment.read_manifest("img") == (
        "# python\nalpha==2\nzeta==1\n# dpkg\nlibc=2.39\n# apk\n# npm-global\n")


def test_trial_image_name_matches_harbor():
    from pennybench.environment import trial_image
    assert trial_image("fizzbuzz__wEcUKDW") == "fizzbuzz__wecukdw__env-main:latest"


def test_prebuilt_cleanup_removes_only_declared_image_without_force(tmp_path, monkeypatch):
    import subprocess
    from pennybench.environment import retire_prebuilt_image
    (tmp_path / "task.toml").write_text('[environment]\ndocker_image = "suite/task:fixed"\n')
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(subprocess, "run", run)
    retire_prebuilt_image(tmp_path)
    assert calls == [["docker", "image", "inspect", "suite/task:fixed"],
                     ["docker", "image", "rm", "suite/task:fixed"]]


@pytest.mark.parametrize("prebuilt", [True, False])
def test_environment_records_prebuilt_without_removing_shared_image(tmp_path, monkeypatch, prebuilt):
    import subprocess
    from pennybench import environment
    task = tmp_path / "task"
    task.mkdir()
    (task / "task.toml").write_text(
        '[environment]\ndocker_image = "suite/task:fixed"\n' if prebuilt else '')
    calls, removed = [], []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0))
    monkeypatch.setattr(environment, "read_manifest", lambda image: calls.append(image) or '# dpkg\nlibc=1\n')
    monkeypatch.setattr(environment, "remove_image", removed.append)
    result = environment.record_environment("trial", tmp_path, task)
    image = "suite/task:fixed" if prebuilt else environment.trial_image("trial")
    assert calls == [image]
    assert removed == ([] if prebuilt else [image])
    assert result["sha256"] and result["error"] is None
    assert (tmp_path / "environment.txt").read_text() == '# dpkg\nlibc=1\n'


def test_long_task_backstop_exceeds_all_phase_limits(tmp_path):
    from pennybench.harbor import task_timeout_s
    (tmp_path / "task.toml").write_text(
        '[environment]\nbuild_timeout_sec = 600\n'
        '[agent]\ntimeout_sec = 12000\n[verifier]\ntimeout_sec = 12000\n')
    assert task_timeout_s(tmp_path) > 600 + 360 + 12000 + 12000
    (tmp_path / "task.toml").write_text('[agent]\ntimeout_sec = 900\n')
    assert task_timeout_s(tmp_path) == 3600


# Cache isolation

def test_cache_nonce_is_stable_per_trial_and_unique_across_trials(tmp_path):
    from pennybench.plan import PlannedTrial
    from pennybench.run import cache_nonce
    a = PlannedTrial(pair=0, position=0, task="t1", rep=0, role="baseline")
    b = PlannedTrial(pair=0, position=1, task="t1", rep=0, role="treatment")
    c = PlannedTrial(pair=1, position=0, task="t1", rep=1, role="baseline")
    run1, run2 = tmp_path / "run1", tmp_path / "run2"
    assert cache_nonce(run1, a) == cache_nonce(run1, a)
    assert len({cache_nonce(run1, a), cache_nonce(run1, b), cache_nonce(run1, c),
                cache_nonce(run2, a)}) == 4


def test_cache_isolation_is_validated_and_defaults_to_none(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy")
    write_tasks(tmp_path, ["t1"])
    assert load_experiment(write_experiment(tmp_path, ["a", "b"], "route"), tmp_path).cache_isolation == "none"
    with pytest.raises(SpecError, match="cache_isolation"):
        load_experiment(write_experiment(tmp_path, ["a", "b"], "route", cache_isolation="run"), tmp_path)


def test_harbor_command_appends_the_isolation_line(tmp_path, config):
    from pennybench.harbor import harbor_command
    arm = load_arm(write_arm(tmp_path, "a"))
    env = build_trial_env(arm, config, ENVIRON)
    argv = harbor_command(arm, tmp_path, tmp_path / "out", env, tmp_path, {}, [], [], "ref abc")
    assert argv[argv.index("--extra-instruction") + 1] == "ref abc"
    assert "--extra-instruction" not in harbor_command(arm, tmp_path, tmp_path / "out", env, tmp_path, {}, [])


def test_include_limits_the_task_set_and_must_name_real_tasks(tmp_path):
    write_arm(tmp_path, "a")
    write_arm(tmp_path, "b", route="endpoint:proxy")
    write_tasks(tmp_path, ["t1", "t2", "t3"])
    exp = load_experiment(write_experiment(tmp_path, ["a", "b"], "route", include=["t2"]), tmp_path)
    assert [p.name for p in exp.task_dirs()] == ["t2"]
    with pytest.raises(SpecError, match="unknown tasks"):
        load_experiment(write_experiment(tmp_path, ["a", "b"], "route", include=["nope"]), tmp_path)


# Usage limits

def test_usage_limit_is_detected_from_claude_codes_own_output(tmp_path):
    from pennybench.run import FINAL_STATUSES, hit_usage_limit
    log = tmp_path / "harbor" / "job" / "trial" / "agent"
    log.mkdir(parents=True)
    (log / "claude-code.txt").write_text('...{"result":"You\'ve hit your session limit · resets 12:40am (UTC)"}')
    assert hit_usage_limit(tmp_path)
    (log / "claude-code.txt").write_text("normal output, task failed for its own reasons")
    assert not hit_usage_limit(tmp_path)
    assert "usage_limit" not in FINAL_STATUSES


# Harbor watchdog

def test_a_hung_harbor_is_killed_and_reported_as_a_retryable_failure(tmp_path):
    import sys, time
    from pennybench.harbor import run_harbor
    start = time.monotonic()
    outcome = run_harbor([sys.executable, "-c", "import time; time.sleep(60)"], {}, tmp_path / "out",
                         tmp_path / "log", timeout_s=1)
    assert outcome.hung and outcome.status == "harbor_failed" and outcome.result is None
    assert time.monotonic() - start < 30
    from pennybench.run import FINAL_STATUSES
    assert outcome.status not in FINAL_STATUSES


def test_a_harbor_that_finishes_is_not_marked_hung(tmp_path):
    import sys
    from pennybench.harbor import run_harbor
    outcome = run_harbor([sys.executable, "-c", "pass"], {}, tmp_path / "out", tmp_path / "log", timeout_s=30)
    assert not outcome.hung and outcome.status == "harbor_failed"  # no result.json was written
