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


def test_sweep_removes_stale_staged_and_trial_copies(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    staged = tmp_path / "tmp" / "pennybench-login-abc"
    staged.mkdir(parents=True)
    (staged / "credentials.json").write_text("{}")
    trial = tmp_path / "run" / "trials" / "t" / "agent" / "sessions"
    trial.mkdir(parents=True)
    (trial / ".credentials.json").write_text("{}")
    removed = cl.sweep_leftovers(tmp_path / "run")
    assert not staged.exists() and not (trial / ".credentials.json").exists() and len(removed) == 2


def test_usage_probe_reads_rate_limit_headers_even_from_a_429(monkeypatch):
    import io
    import urllib.error
    from email.message import Message

    def headers(**values):
        m = Message()
        for k, v in values.items():
            m[k.replace("_", "-")] = v
        return m

    base = {"anthropic-ratelimit-unified-5h-utilization": "0.71",
            "anthropic-ratelimit-unified-7d-utilization": "0.2",
            "anthropic-ratelimit-unified-5h-reset": "1792388400",
            "anthropic-ratelimit-unified-7d-reset": "1792551600"}
    m = Message()
    for k, v in base.items():
        m[k] = v

    class Response:
        headers = m

    monkeypatch.setattr(cl.urllib.request, "urlopen", lambda *a, **k: Response())
    login = cl.Login(oauth={"accessToken": "at", "refreshToken": "rt"})
    usage = cl.probe_usage(login)
    assert usage["five_hour"] == 0.71 and usage["five_hour_reset"] == 1792388400

    def raise429(*a, **k):
        raise urllib.error.HTTPError("u", 429, "limit", m, io.BytesIO(b"{}"))
    monkeypatch.setattr(cl.urllib.request, "urlopen", raise429)
    assert cl.probe_usage(login)["seven_day"] == 0.2

    def offline(*a, **k):
        raise urllib.error.URLError("no network")
    monkeypatch.setattr(cl.urllib.request, "urlopen", offline)
    assert cl.probe_usage(login) is None


def test_usage_stop_reason_names_the_window_and_continues_when_unknown():
    usage = {"five_hour": 0.71, "seven_day": 0.2, "five_hour_reset": 1792388400, "seven_day_reset": 1792551600}
    assert "5-hour usage is 71%" in cl.usage_stop_reason(usage, 0.7)
    assert cl.usage_stop_reason(usage, 0.8) is None
    assert "7-day usage is 90%" in cl.usage_stop_reason({**usage, "five_hour": 0.1, "seven_day": 0.9}, 0.7)
    assert cl.usage_stop_reason(None, 0.7) is None


def test_login_plan_is_non_secret_and_audit_flags_arms_on_different_plans(tmp_path):
    login = cl.Login(oauth={"accessToken": "SECRET-ACCESS", "refreshToken": "SECRET-REFRESH",
                            "subscriptionType": "pro", "rateLimitTier": "default_claude_ai"})
    assert login.plan == {"subscription": "pro", "rate_limit_tier": "default_claude_ai"}
    assert "SECRET" not in json.dumps(login.plan)
