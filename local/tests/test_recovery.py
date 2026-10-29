"""Recovery harness safeguards; these tests never contact Docker or banking."""
from pathlib import Path
import runpy
import json
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = runpy.run_path(str(ROOT / 'recovery.py'))
validate = RECOVERY['validate_fixture']
PROJECT = 'bankops-step68-123456abcdef'


def fixture():
    services = {name: {'environment': {}, 'networks': {}} for name in RECOVERY['RUNTIME'] | {'prepare', 'migrate', 'grant'}}
    services['agent']['environment'] = {'BANKOPS_AGENT_LLM_PROVIDER': 'disabled', 'BANKOPS_AGENT_REMEDIATION_ENABLED': 'false'}
    services['banking']['environment']['BANKOPS_CUSTOMER_ENABLED'] = 'false'
    return {'name': PROJECT, 'services': services, 'volumes': {'financial': {'name': PROJECT + '_financial'}},
            'networks': {'financial': {'name': PROJECT + '_financial'}}}


def test_isolated_fixture_accepted():
    validate(fixture(), PROJECT)


@pytest.mark.parametrize('project', ['bankops-ai', 'bankops-step67-123456abcdef', 'bankops-step68-existing', ''])
def test_existing_projects_rejected(project):
    with pytest.raises(ValueError):
        validate(fixture(), project)


@pytest.mark.parametrize('kind', ['volumes', 'networks'])
def test_external_infrastructure_rejected(kind):
    config = fixture()
    config[kind]['financial']['external'] = True
    with pytest.raises(ValueError):
        validate(config, PROJECT)


def test_retained_volume_rejected():
    config = fixture()
    config['volumes']['financial']['name'] = 'bankops-ai_bankops_postgres_data'
    with pytest.raises(ValueError):
        validate(config, PROJECT)


@pytest.mark.parametrize('change', ['public_port', 'writable_bind', 'admin_secret', 'agent_network', 'agent_password'])
def test_unsafe_service_configuration_rejected(change):
    config = fixture()
    if change == 'public_port':
        config['services']['frontend']['ports'] = [{'host_ip': '0.0.0.0'}]
    elif change == 'writable_bind':
        config['services']['postgres']['volumes'] = [{'type': 'bind', 'source': '/existing'}]
    elif change == 'admin_secret':
        config['services']['banking']['environment']['BANKOPS_POSTGRES_ADMIN_PASSWORD'] = 'secret'
    elif change == 'agent_network':
        config['services']['agent']['networks']['financial'] = None
    else:
        config['services']['agent']['environment']['BANKOPS_DB_PASSWORD'] = 'secret'
    with pytest.raises(ValueError):
        validate(config, PROJECT)


def test_credentials_fresh_private_and_not_overwritten(tmp_path):
    generate = runpy.run_path(str(ROOT / 'init.py'))['generate']
    values = generate(tmp_path, 'bankops-step68-')
    assert values['BANKOPS_LOCAL_PROJECT'].startswith('bankops-step68-')
    passwords = [v for k, v in values.items() if k.endswith('PASSWORD')]
    assert len(set(passwords)) == len(passwords)
    before = (tmp_path / '.env.local').read_bytes()
    with pytest.raises(SystemExit):
        generate(tmp_path, 'bankops-step68-')
    assert before == (tmp_path / '.env.local').read_bytes()


def test_retry_poll_is_read_only_and_tolerates_transient_failure(monkeypatch):
    wait = RECOVERY['wait_for']
    monkeypatch.setattr(RECOVERY['time'], 'sleep', lambda _: None)
    attempts = iter([False, False, 'recovered'])
    assert wait(lambda: next(attempts), timeout=1) == 'recovered'


def test_recovery_replay_keeps_original_request_and_key():
    run = object.__new__(RECOVERY['Recovery'])
    run.key = 'original-key'
    run.transfer_body = {'sourceAccountId': 'source', 'destinationAccountId': 'destination', 'amount': 250}
    run.transfer = {'id': 'original-transfer'}
    run.replay_statuses = []
    replies = iter([(503, None), (200, {'id': 'original-transfer'})])
    requests = []
    def api(*arguments):
        requests.append(arguments)
        return next(replies)
    run.api = api
    assert run.replay_completed_transfer() is False
    assert run.replay_completed_transfer() is True
    assert run.replay_statuses == [503, 200]
    assert requests[0] == requests[1]
    assert requests[0][-1] == {'Idempotency-Key': 'original-key'}


def test_recovery_replay_rejects_duplicate_transfer_identity():
    run = object.__new__(RECOVERY['Recovery'])
    run.key, run.transfer_body, run.transfer, run.replay_statuses = 'key', {}, {'id': 'original'}, []
    run.api = lambda *args: (200, {'id': 'duplicate'})
    with pytest.raises(AssertionError):
        run.replay_completed_transfer()


def test_explicit_subnets_avoid_existing_networks_without_cleanup():
    allocate = RECOVERY['isolated_subnets']
    assert allocate(['172.16.0.0/12', '10.68.0.0/23'], 2) == ['10.68.2.0/24', '10.68.3.0/24']


def test_subnet_exhaustion_fails_without_deleting_networks():
    with pytest.raises(ValueError):
        RECOVERY['isolated_subnets'](['10.0.0.0/8'], 1)


def test_host_and_none_network_metadata_do_not_hide_used_subnets():
    networks = [{'IPAM': {'Config': None}}, {'IPAM': None}, {'IPAM': {'Config': [{'Subnet': '10.68.0.0/24'}]}}]
    assert RECOVERY['docker_subnets'](networks) == ['10.68.0.0/24']


def test_chromium_worker_closes_with_input_pipe_still_open():
    process = subprocess.Popen(['node', str(ROOT / 'browser-recovery.mjs')], cwd=ROOT.parent,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        process.stdin.write(json.dumps({'command': 'close'}) + '\n')
        process.stdin.flush()
        assert json.loads(process.stdout.readline())['ok']
        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()
