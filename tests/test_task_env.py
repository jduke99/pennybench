import pytest

from pennybench.config import ConfigError
from pennybench.spec import SpecError
from pennybench.task_env import TaskEnv, parse_task_env


def test_secrets_reach_host_env_and_are_returned_for_scanning():
    env = parse_task_env({"secrets": ["OPENAI_API_KEY"], "values": {"TAU2_USER_MODEL": "m"}}, "x")
    host, secrets = env.host_env({"OPENAI_API_KEY": "sk-1"})
    assert host == {"TAU2_USER_MODEL": "m", "OPENAI_API_KEY": "sk-1"}
    assert secrets == ("sk-1",)


def test_record_names_secrets_but_never_holds_their_values():
    env = parse_task_env({"secrets": ["OPENAI_API_KEY"], "values": {"A": "1"}}, "x")
    assert env.record() == {"secrets": ["OPENAI_API_KEY"], "values": {"A": "1"}}


def test_missing_secret_is_refused():
    with pytest.raises(ConfigError):
        TaskEnv(secrets=("OPENAI_API_KEY",), values={}).host_env({})


def test_agent_variables_and_duplicates_are_refused():
    with pytest.raises(SpecError):
        parse_task_env({"secrets": ["ANTHROPIC_API_KEY"]}, "x")
    with pytest.raises(SpecError):
        parse_task_env({"secrets": ["A"], "values": {"A": "1"}}, "x")
    with pytest.raises(SpecError):
        parse_task_env({"other": 1}, "x")


def test_absent_task_env_is_empty():
    assert parse_task_env(None, "x").host_env({}) == ({}, ())


def test_sidecar_hosts_come_from_declared_mcp_servers(tmp_path):
    from pennybench.harbor import sidecar_hosts
    (tmp_path / "task.toml").write_text(
        '[[environment.mcp_servers]]\nname = "a"\nurl = "http://tau3-runtime:8000/mcp"\n')
    assert sidecar_hosts(tmp_path) == ["tau3-runtime"]
    (tmp_path / "task.toml").write_text("[agent]\ntimeout_sec = 1\n")
    assert sidecar_hosts(tmp_path) == []
