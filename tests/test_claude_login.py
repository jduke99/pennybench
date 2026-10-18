import json
import time

import pytest

from pennybench import claude_login as cl


@pytest.fixture
def store(monkeypatch):
    data = {"claudeAiOauth": {"accessToken": "at-1", "refreshToken": "rt-1",
                              "expiresAt": (time.time() + 7200) * 1000},
            "mcpOAuth": {"some-server": {"accessToken": "mcp-secret"}}}
    writes = []
    monkeypatch.setattr(cl, "_read_store", lambda: json.loads(json.dumps(data)))
    monkeypatch.setattr(cl, "_write_store", lambda s: writes.append(s))
    return data, writes


def test_only_the_claude_ai_login_is_staged_and_the_copy_is_removed(store):
    staged = cl.StagedLogin(cl.load_login(30))
    copied = json.loads(staged.path.read_text())
    assert copied == {"claudeAiOauth": store[0]["claudeAiOauth"]}
    assert staged.mounts()[0]["target"] == "/pennybench/login" and staged.mounts()[0]["read_only"]
    path = staged.path
    assert staged.close(path.parent.parent / "no-trial") == {"refreshed": False}
    assert not path.exists() and not path.parent.exists()
    assert store[1] == []


def test_a_refresh_inside_the_trial_is_written_back_keeping_other_entries(store, tmp_path):
    staged = cl.StagedLogin(cl.load_login(30))
    sessions = tmp_path / "agent" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "at-2", "refreshToken": "rt-2"}}))
    assert staged.close(tmp_path) == {"refreshed": True}
    assert store[1][0]["claudeAiOauth"]["refreshToken"] == "rt-2"
    assert store[1][0]["mcpOAuth"] == store[0]["mcpOAuth"]


def test_login_near_expiry_is_refused(store, monkeypatch):
    store[0]["claudeAiOauth"]["expiresAt"] = (time.time() + 600) * 1000
    with pytest.raises(cl.LoginError, match="expires in"):
        cl.load_login(30)


def test_copies_in_trial_logs_are_removed(tmp_path):
    nested = tmp_path / "harbor" / "job" / "t" / "agent" / "sessions"
    nested.mkdir(parents=True)
    (nested / ".credentials.json").write_text("{}")
    assert cl.remove_copies(tmp_path) == ["harbor/job/t/agent/sessions/.credentials.json"]
    assert not (nested / ".credentials.json").exists()
