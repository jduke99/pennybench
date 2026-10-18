"""Harbor's Claude Code agent, plus installing a staged claude.ai login before the run.

Harbor bind-mounts the trial's agent log directory, which contains $CLAUDE_CONFIG_DIR, so a
file cannot be mounted into the config directory directly. The login is mounted read-only at
LOGIN_DIR instead and copied into place by the agent's own setup step. The copy therefore
lands in the trial's log directory on the host, where the runner removes it after the trial.
"""

from __future__ import annotations

from harbor.agents.installed.claude_code import ClaudeCode

LOGIN_DIR = "/pennybench/login"
LOGIN_FILE = "credentials.json"
IMPORT_PATH = "pennybench.harbor_agent:SignedInClaudeCode"


class SignedInClaudeCode(ClaudeCode):
    def _build_register_mcp_servers_command(self) -> str | None:
        install = (f"(test -f {LOGIN_DIR}/{LOGIN_FILE} && "
                   f"cp {LOGIN_DIR}/{LOGIN_FILE} $CLAUDE_CONFIG_DIR/.credentials.json && "
                   "chmod 600 $CLAUDE_CONFIG_DIR/.credentials.json)")
        mcp = super()._build_register_mcp_servers_command()
        return f"{install} && {mcp}" if mcp else install
