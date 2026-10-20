"""Evidence-based failure labels rebuilt from artifacts, without changing outcomes."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def classify_failure(trial_dir: Path, record: dict, harbor: dict) -> dict | None:
    info = harbor.get('exception_info') or {}
    exception_type = info.get('exception_type') or record.get('exception_type')
    terminal = None
    for path in sorted(trial_dir.glob('harbor/**/agent/claude-code.txt')):
        for line in path.open():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get('type') == 'result':
                terminal = event
    category = None
    evidence = None
    provider_message_id = None
    if terminal and terminal.get('stop_reason') == 'refusal':
        category = 'provider_safeguard_refusal'
        evidence = 'CLI terminal result: stop_reason=refusal'
        match = re.search(r'Message ID:\s*(msg_[\w-]+)', terminal.get('result') or '')
        provider_message_id = match.group(1) if match else None
    if category is None and (exception_type or record.get('status') == 'agent_error'):
        wire = trial_dir / 'wire' / 'wire.jsonl'
        if wire.exists():
            last_flow = None
            for line in wire.open():
                try:
                    flow = json.loads(line)
                except ValueError:
                    continue
                if '/v1/messages' in flow.get('path', ''):
                    last_flow = flow
            if last_flow is not None:
                status = last_flow.get('status')
                # Only explicit HTTP failure evidence, never quota metadata saying allowed.
                if status in (401, 403, 402, 429):
                    category = {401: 'authentication_error', 403: 'authentication_error',
                                402: 'billing_limit', 429: 'rate_limit'}[status]
                    evidence = f'Gateway capture: HTTP {status}'
    if category is None:
        if exception_type == 'VerifierTimeoutError':
            category = 'verifier_timeout'
        elif exception_type == 'AgentTimeoutError':
            category = 'agent_timeout'
        elif harbor.get('environment_setup') and not harbor.get('agent_execution') and exception_type:
            category = 'environment_setup_failure'
        elif exception_type:
            detail = info.get('exception_message') or info.get('exception_traceback') or ''
            if 'Docker compose command failed' in detail and 'up --detach' in detail:
                category = 'environment_setup_failure'
            else:
                category = 'unknown_api_or_execution_error'
        elif record.get('status') == 'agent_error':
            category = 'unknown_api_or_execution_error'
        if category:
            evidence = f'Harbor exception: {exception_type or "unspecified"}'
    if category is None:
        return None
    findings = []
    if (exception_type == 'AgentTimeoutError' and terminal
            and terminal.get('terminal_reason') == 'completed'
            and not terminal.get('is_error')):
        findings.append('cli_completed_before_execution_timeout')
    return {'category': category, 'evidence': evidence,
            'exception_type': exception_type, 'provider_message_id': provider_message_id,
            'diagnostic_findings': findings}


def outcome_summary(trials: list[dict]) -> dict:
    roles = defaultdict(list)
    for trial in trials:
        roles[trial['role']].append(trial)
    result = {}
    for role, rows in roles.items():
        failures = Counter(t['failure']['category'] for t in rows if t.get('failure'))
        result[role] = {
            'trials': len(rows),
            'successes': sum(t['metrics']['reward'] == 1 for t in rows),
            'scored_failures': sum(t['metrics']['reward'] == 0 for t in rows),
            'missing_rewards': sum(t['metrics']['reward'] is None for t in rows),
            'failure_categories': dict(sorted(failures.items())),
            'cost_on_failed_or_unscored_trials': sum(
                t['metrics']['cost'] for t in rows if t['metrics']['reward'] != 1),
            'unstarted_trials': sum(t['metrics']['turns'] == 0 and t['status'] != 'complete'
                                    for t in rows),
        }
    return result


def format_outcomes(summary: dict) -> str:
    lines = ['Outcomes (original rewards unchanged; error categories may overlap scored failures):']
    for role, counts in summary.items():
        lines.append(f"  {role}: {counts['successes']}/{counts['trials']} successes; "
                     f"{counts['scored_failures']} scored failures; "
                     f"{counts['missing_rewards']} missing rewards; "
                     f"{counts['unstarted_trials']} unstarted")
        for category, count in counts['failure_categories'].items():
            lines.append(f'    {category}: {count}')
        lines.append(f"    spending on failed/unscored trials: "
                     f"${counts['cost_on_failed_or_unscored_trials']:.4f}")
    lines.append('Cost comparisons include failed/unstarted runs; lower spending can reflect failure.')
    return '\n'.join(lines)
