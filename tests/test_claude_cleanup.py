import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from harbor.agents.installed.claude_code import ClaudeCode
from pennybench.claude_cleanup import terminal_result
from pennybench.harbor_agent import SignedInClaudeCode


def test_terminal_result_ignores_partial_and_intermediate_records(tmp_path):
    path = tmp_path / 'cli.jsonl'
    path.write_text('{"type":"result","terminal_reason":"not_terminal"}\n{"type":')
    assert terminal_result(path) is None
    result = {'type': 'result', 'terminal_reason': 'completed', 'is_error': False}
    path.write_text(json.dumps(result) + '\n{"partial":')
    assert terminal_result(path) == result


@pytest.mark.parametrize('terminal_error', [False, True])
def test_lingering_execution_is_stopped_and_recorded(tmp_path, monkeypatch, terminal_error):
    async def scenario():
        stopped = asyncio.Event()
        commands = []

        async def execute(self, environment, command, **kwargs):
            commands.append(command)
            # Simulate the group created by the wrapper and an inherited pipe
            # remaining open after the CLI writes its result.
            import re
            pid_name = re.search(r'claude-execution-[a-f0-9]+\.pid', command)[0]
            (tmp_path / pid_name).write_text('12345')
            (tmp_path / 'claude-code.txt').write_text(json.dumps({
                'type': 'result', 'terminal_reason': 'api_error' if terminal_error else 'completed',
                'is_error': terminal_error,
            }) + '\n')
            await stopped.wait()
            raise RuntimeError('Execution terminated by cleanup')

        async def cleanup(**kwargs):
            commands.append(kwargs['command'])
            stopped.set()

        monkeypatch.setattr(ClaudeCode, 'exec_as_agent', execute)
        agent = object.__new__(SignedInClaudeCode)
        agent.logs_dir = tmp_path
        agent.environment_logs_dir = tmp_path
        agent.cleanup_grace_sec = 0
        environment = SimpleNamespace(exec=cleanup)
        if terminal_error:
            with pytest.raises(RuntimeError, match='terminal result'):
                await agent.exec_as_agent(environment, 'claude --verbose --output-format=stream-json --print')
        else:
            await agent.exec_as_agent(environment, 'claude --verbose --output-format=stream-json --print')
            # Normal return lets Harbor proceed to verification; no reward is assigned here.
        audit = json.loads((tmp_path / 'claude-cleanup.json').read_text())
        assert audit['cleanup_exceeded_grace'] is True
        assert 'kill -TERM -- -12345' in commands[-1]
        assert 'kill -KILL -- -12345' in commands[-1]
        assert 'docker' not in commands[-1]
    asyncio.run(scenario())


def test_natural_exit_does_not_trigger_cleanup(tmp_path, monkeypatch):
    async def execute(self, environment, command, **kwargs):
        return 'normal exit'
    monkeypatch.setattr(ClaudeCode, 'exec_as_agent', execute)
    agent = object.__new__(SignedInClaudeCode)
    agent.logs_dir = tmp_path
    agent.environment_logs_dir = tmp_path
    assert asyncio.run(agent.exec_as_agent(None, 'claude --verbose --output-format=stream-json --print')) == 'normal exit'
    assert not json.loads((tmp_path / 'claude-cleanup.json').read_text())['cleanup_exceeded_grace']


@pytest.mark.skipif(sys.platform == 'win32', reason='needs /bin/bash')
def test_real_inherited_pipe_is_released(tmp_path, monkeypatch):
    """A CLI can exit while a child keeps Docker's captured output open."""
    import shlex

    async def scenario():
        async def execute(self, environment, command, **kwargs):
            process = await asyncio.create_subprocess_shell(
                command, executable='/bin/bash',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                await process.communicate()
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            if process.returncode:
                raise RuntimeError('terminated')

        async def cleanup(command, **kwargs):
            process = await asyncio.create_subprocess_exec('/bin/bash', '-c', command)
            await process.wait()

        monkeypatch.setattr(ClaudeCode, 'exec_as_agent', execute)
        agent = object.__new__(SignedInClaudeCode)
        agent.logs_dir = tmp_path
        agent.environment_logs_dir = tmp_path
        agent.cleanup_grace_sec = 0.1
        log = shlex.quote(str(tmp_path / 'claude-code.txt'))
        # The comment triggers the same wrapper interception as Harbor's command.
        command = ('sleep 30 & printf \'%s\\n\' '
                   + shlex.quote(json.dumps({'type': 'result', 'terminal_reason': 'completed', 'is_error': False}))
                   + f' > {log} # claude --verbose --output-format=stream-json --print')
        await asyncio.wait_for(agent.exec_as_agent(SimpleNamespace(exec=cleanup), command), 8)
        assert json.loads((tmp_path / 'claude-cleanup.json').read_text())['cleanup_exceeded_grace']
    asyncio.run(scenario())


def test_without_terminal_result_outer_timeout_remains_an_error(tmp_path, monkeypatch):
    async def execute(self, environment, command, **kwargs):
        await asyncio.Event().wait()
    monkeypatch.setattr(ClaudeCode, 'exec_as_agent', execute)
    agent = object.__new__(SignedInClaudeCode)
    agent.logs_dir = tmp_path
    agent.environment_logs_dir = tmp_path

    async def scenario():
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(agent.exec_as_agent(
                None, 'claude --verbose --output-format=stream-json --print'), .05)
    asyncio.run(scenario())
    audit = json.loads((tmp_path / 'claude-cleanup.json').read_text())
    assert not audit['terminal_result_seen']
    assert not audit['cleanup_exceeded_grace']
