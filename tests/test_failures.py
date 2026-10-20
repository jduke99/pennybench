import json

import pytest

from pennybench.failures import classify_failure, outcome_summary, format_outcomes


def test_refusal_preserves_provider_id(tmp_path):
    path = tmp_path / 'harbor' / 'trial' / 'agent' / 'claude-code.txt'
    path.parent.mkdir(parents=True)
    path.write_text('partial\n' + json.dumps({
        'type': 'result', 'stop_reason': 'refusal',
        'result': 'Safeguards flagged this message. Message ID: msg_example',
    }) + '\n')
    record = {'status': 'agent_error', 'exception_type': 'UnknownApiError', 'reward': 0}
    failure = classify_failure(tmp_path, record, {})
    assert failure['category'] == 'provider_safeguard_refusal'
    assert failure['provider_message_id'] == 'msg_example'
    assert record['reward'] == 0


@pytest.mark.parametrize('exception,category', [
    ('AgentTimeoutError', 'agent_timeout'),
    ('VerifierTimeoutError', 'verifier_timeout'),
    ('UnknownApiError', 'unknown_api_or_execution_error'),
])
def test_exception_categories(tmp_path, exception, category):
    assert classify_failure(tmp_path, {'status': 'agent_error', 'exception_type': exception}, {})['category'] == category


def test_environment_setup_failure(tmp_path):
    harbor = {'exception_info': {'exception_type': 'RuntimeError',
              'exception_message': 'Docker compose command failed: up --detach --wait; DNS failure'}}
    assert classify_failure(tmp_path, {'status': 'agent_error'}, harbor)['category'] == 'environment_setup_failure'


@pytest.mark.parametrize('status,category', [(401, 'authentication_error'), (402, 'billing_limit'), (429, 'rate_limit')])
def test_explicit_http_failure(tmp_path, status, category):
    wire = tmp_path / 'wire' / 'wire.jsonl'
    wire.parent.mkdir()
    wire.write_text(json.dumps({'path': '/v1/messages', 'status': status}) + '\n')
    assert classify_failure(tmp_path, {'status': 'agent_error'}, {})['category'] == category
    # A successful retry is not an outage cause.
    with wire.open('a') as f:
        f.write(json.dumps({'path': '/v1/messages', 'status': 200}) + '\n')
    assert classify_failure(tmp_path, {'status': 'agent_error'}, {})['category'] == 'unknown_api_or_execution_error'


def test_task_failure_is_not_execution_failure(tmp_path):
    assert classify_failure(tmp_path, {'status': 'complete', 'reward': 0}, {}) is None


def test_summary_keeps_scores_separate_from_causes():
    rows = [{'role': 'treatment', 'status': 'agent_error',
             'failure': {'category': 'provider_safeguard_refusal'},
             'metrics': {'reward': 0, 'cost': .01, 'turns': 1}},
            {'role': 'treatment', 'status': 'agent_error', 'failure': {'category': 'environment_setup_failure'},
             'metrics': {'reward': None, 'cost': 0, 'turns': 0}}]
    summary = outcome_summary(rows)
    assert summary['treatment']['scored_failures'] == 1
    assert summary['treatment']['missing_rewards'] == 1
    assert summary['treatment']['unstarted_trials'] == 1
    assert 'lower spending can reflect failure' in format_outcomes(summary)
