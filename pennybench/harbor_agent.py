"""Harbor's Claude Code agent, plus installing a staged claude.ai login before the run.

Harbor bind-mounts the trial's agent log directory, which contains $CLAUDE_CONFIG_DIR, so a
file cannot be mounted into the config directory directly. The login is mounted read-only at
LOGIN_DIR instead and copied into place by the agent's own setup step. The copy therefore
lands in the trial's log directory on the host, where the runner removes it after the trial.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time
import uuid

from harbor.agents.installed.claude_code import ClaudeCode
from pennybench.claude_cleanup import terminal_result

LOGIN_DIR = "/pennybench/login"
LOGIN_FILE = "credentials.json"
IMPORT_PATH = "pennybench.harbor_agent:SignedInClaudeCode"


class SignedInClaudeCode(ClaudeCode):
    cleanup_grace_sec = 5.0

    async def exec_as_agent(self, environment, command, **kwargs):
        if 'claude --verbose --output-format=stream-json ' not in command:
            return await super().exec_as_agent(environment, command, **kwargs)

        # Bash job control gives this execution its own process group. Do not kill
        # the container: Harbor must still run its verifier in that environment.
        pid_name = f'claude-execution-{uuid.uuid4().hex}.pid'
        remote_pid = self.environment_logs_dir / pid_name
        local_pid = self.logs_dir / pid_name
        wrapped = ('set -m; ( set -o pipefail; ' + command + '\n ) & '
                   'pennybench_pid=$!; printf "%s" "$pennybench_pid" > '
                   + shlex.quote(str(remote_pid)) + '; wait "$pennybench_pid"')
        task = asyncio.create_task(super().exec_as_agent(
            environment, 'bash -c ' + shlex.quote(wrapped), **kwargs))
        record = None
        observed = None
        exceeded = False
        cleanup_error = None
        try:
            while not task.done():
                if record is None:
                    record = terminal_result(self.logs_dir / 'claude-code.txt')
                    if record is not None:
                        observed = time.monotonic()
                if observed is not None and time.monotonic() - observed >= self.cleanup_grace_sec:
                    exceeded = True
                    pid = int(local_pid.read_text())
                    if pid <= 1:
                        raise ValueError('Invalid Claude execution process group')
                    # TERM first, then KILL the isolated execution group, including
                    # children that still hold stdout/stderr open after CLI exit.
                    await environment.exec(command=(
                        f'kill -TERM -- -{pid} 2>/dev/null || true; '
                        f'sleep 1; kill -KILL -- -{pid} 2>/dev/null || true'),
                        timeout_sec=5)
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=5)
                    except Exception as exc:
                        cleanup_error = type(exc).__name__
                        task.cancel()
                    if record.get('is_error') or record.get('terminal_reason') != 'completed':
                        raise RuntimeError('Claude terminal result reported an error')
                    return None
                await asyncio.wait({task}, timeout=0.2)
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            record = record or terminal_result(self.logs_dir / 'claude-code.txt')
            (self.logs_dir / 'claude-cleanup.json').write_text(json.dumps({
                'terminal_result_seen': record is not None,
                'terminal_reason': record.get('terminal_reason') if record else None,
                'grace_seconds': self.cleanup_grace_sec,
                'cleanup_exceeded_grace': exceeded,
                'cleanup_error': cleanup_error,
            }, indent=2) + '\n')
            local_pid.unlink(missing_ok=True)

    def _build_register_mcp_servers_command(self) -> str | None:
        install = (f"(test -f {LOGIN_DIR}/{LOGIN_FILE} && "
                   f"cp {LOGIN_DIR}/{LOGIN_FILE} $CLAUDE_CONFIG_DIR/.credentials.json && "
                   "chmod 600 $CLAUDE_CONFIG_DIR/.credentials.json)")
        mcp = super()._build_register_mcp_servers_command()
        return f"{install} && {mcp}" if mcp else install
