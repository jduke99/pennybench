"""A real claude.ai login for Claude Code inside a trial, as a signed-in user would run it.

Claude Code signed in to claude.ai behaves differently from one given a bare token: it has
the account's tools (for example Artifact), and a proxy recognizes the linked account. To
measure what signed-in users get, each trial receives a copy of the runner's own login.

Only the `claudeAiOauth` entry is copied; other stored sign-ins (MCP servers) never leave the
host. The copy is mounted where Claude Code reads it and deleted after the trial. If Claude
Code refreshed the login during the trial, the refresh token has rotated, so the new tokens
are written back to the host store; otherwise the host's own Claude Code would be signed out.
"""

from __future__ import annotations

import json
import os

from pennybench.harbor_agent import LOGIN_DIR, LOGIN_FILE
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

KEYCHAIN_SERVICE = "Claude Code-credentials"
LINUX_CREDENTIALS = Path.home() / ".claude" / ".credentials.json"


class LoginError(RuntimeError):
    pass


def _read_store() -> dict:
    if os.uname().sysname == "Darwin":
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            raise LoginError("no Claude Code login in the macOS Keychain; run `claude auth login`")
        return json.loads(out.stdout)
    if not LINUX_CREDENTIALS.exists():
        raise LoginError(f"no Claude Code login at {LINUX_CREDENTIALS}; run `claude auth login`")
    return json.loads(LINUX_CREDENTIALS.read_text())


def _write_store(store: dict) -> None:
    text = json.dumps(store, separators=(",", ":"))
    if os.uname().sysname == "Darwin":
        account = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE],
                                 capture_output=True, text=True).stdout
        acct = next((line.split("=", 1)[1].strip().strip('"') for line in account.splitlines()
                     if '"acct"' in line), os.environ.get("USER", ""))
        out = subprocess.run(["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE,
                              "-a", acct, "-w", text], capture_output=True, text=True)
        if out.returncode != 0:
            raise LoginError(f"could not update the Keychain login: {out.stderr.strip()}")
        return
    LINUX_CREDENTIALS.write_text(text)
    LINUX_CREDENTIALS.chmod(0o600)


@dataclass
class Login:
    oauth: dict

    @property
    def secrets(self) -> tuple[str, ...]:
        return tuple(v for v in (self.oauth.get("accessToken"), self.oauth.get("refreshToken")) if v)

    @property
    def minutes_left(self) -> float:
        expires = self.oauth.get("expiresAt")
        return (expires / 1000 - time.time()) / 60 if expires else 0.0


def load_login(min_minutes: float = 0) -> Login:
    oauth = _read_store().get("claudeAiOauth") or {}
    if not oauth.get("accessToken") or not oauth.get("refreshToken"):
        raise LoginError("the Claude Code login has no claude.ai tokens; run `claude auth login`")
    login = Login(oauth=oauth)
    if login.minutes_left < min_minutes:
        raise LoginError(
            f"the Claude Code login expires in {login.minutes_left:.0f} min, under the "
            f"{min_minutes:.0f} min a trial needs; run `claude auth status` or start `claude` "
            "once to refresh it, then retry")
    return login


def ensure_login(min_minutes: float) -> Login:
    """The current login, after offering an interactive `claude auth login` if there is none."""
    try:
        return load_login(min_minutes)
    except LoginError as first:
        if not os.isatty(0) or "run `claude auth login`" not in str(first):
            raise
        print(f"pennybench: {first}\nStarting `claude auth login`...", flush=True)
        subprocess.run(["claude", "auth", "login"])
        return load_login(min_minutes)


class StagedLogin:
    """A private copy of the login for one trial, mounted read-only at LOGIN_DIR; the agent
    copies it into Claude Code's config directory (see harbor_agent). `close()` syncs a
    refresh made during the trial back to the host store and deletes the staged copy."""

    def __init__(self, login: Login):
        self.login = login
        self._dir = tempfile.mkdtemp(prefix="pennybench-login-")
        os.chmod(self._dir, 0o700)
        self.path = Path(self._dir) / LOGIN_FILE
        self.path.write_text(json.dumps({"claudeAiOauth": login.oauth}))
        self.path.chmod(0o600)

    def mounts(self) -> list[dict]:
        return [{"type": "bind", "source": self._dir, "target": LOGIN_DIR, "read_only": True}]

    def close(self, trial_dir: Path) -> dict:
        """Returns {"refreshed": bool}. Claude Code refreshes the copy in its config
        directory, which Harbor keeps in the trial's logs. Always removes the staged copy."""
        refreshed = False
        try:
            for copy in trial_dir.rglob(".credentials.json"):
                after = json.loads(copy.read_text()).get("claudeAiOauth") or {}
                if (after.get("refreshToken")
                        and after.get("refreshToken") != self.login.oauth.get("refreshToken")):
                    store = _read_store()
                    store["claudeAiOauth"] = after
                    _write_store(store)
                    refreshed = True
        finally:
            for p in Path(self._dir).glob("*"):
                p.unlink()
            os.rmdir(self._dir)
        return {"refreshed": refreshed}


def remove_copies(directory: Path) -> list[str]:
    """Delete every credentials file Harbor copied back with the trial logs."""
    removed = []
    for path in directory.rglob(".credentials.json"):
        path.unlink()
        removed.append(str(path.relative_to(directory)))
    return removed


def sweep_leftovers(run_dir: Path) -> list[str]:
    """Remove login copies a stopped run left behind: staged copies in the temp directory and
    copies Harbor brought back into the run's trial logs. Runs start one at a time, so any
    staged copy that exists before a run starts is stale."""
    removed = []
    for staged in Path(tempfile.gettempdir()).glob("pennybench-login-*"):
        for p in staged.glob("*"):
            p.unlink()
        staged.rmdir()
        removed.append(str(staged))
    if run_dir.exists():
        removed += [str(run_dir / r) for r in remove_copies(run_dir)]
    return removed
