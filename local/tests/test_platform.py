"""Network non-interference, diagnostics and log privacy of the local launcher."""
import copy
import subprocess
from pathlib import Path
import runpy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / 'platform.py'))
plan = MODULE['network_plan']
LocalError = MODULE['LocalError']
PROJECT = 'bankops-step67-123456abcdef'


def config():
    return {'name': PROJECT, 'networks': {k: {'name': PROJECT + '_' + k} for k in ('financial', 'web')}}


def network(key, subnet='172.20.0.0/16', owner=PROJECT):
    return {'Name': PROJECT + '_' + key, 'Labels': {'com.docker.compose.project': owner}, 'IPAM': {'Config': [{'Subnet': subnet}]}}


def test_adoption_does_not_add_ipam_or_change_existing_networks():
    existing = [network('financial'), network('web', '172.21.0.0/16')]
    before = copy.deepcopy(existing)
    result = plan(config(), existing, None)
    assert result['overlay']['networks'] == {}
    assert result['adopted'] == ['financial', 'web']
    assert existing == before


def test_only_missing_network_receives_unused_explicit_subnet():
    result = plan(config(), [network('financial', '10.69.0.0/24')], '10.69.0.0/16')
    assert set(result['overlay']['networks']) == {'web'}
    assert result['overlay']['networks']['web']['ipam']['config'] == [{'subnet': '10.69.1.0/24'}]


def test_saved_plan_reused_without_reallocation():
    original = plan(config(), [], '192.168.200.0/21')
    existing = [network(k, v['ipam']['config'][0]['subnet']) for k, v in original['overlay']['networks'].items()]
    assert plan(config(), existing, None, original) == original


def test_pool_change_for_existing_project_rejected():
    original = plan(config(), [], None)
    with pytest.raises(LocalError, match='already fixed'):
        plan(config(), [], '192.168.200.0/21', original)


def test_existing_network_drift_rejected_without_mutation():
    original = plan(config(), [], None)
    with pytest.raises(LocalError, match='differs'):
        plan(config(), [network('financial', '192.168.1.0/24')], None, original)


@pytest.mark.parametrize('saved', [False, True])
def test_other_project_network_never_attached_or_modified(saved):
    original = plan(config(), [], None) if saved else None
    with pytest.raises(LocalError, match='owned'):
        plan(config(), [network('financial', owner='other-project')], None, original)


@pytest.mark.parametrize('pool', ['8.8.0.0/16', '0.0.0.0/0', '10.0.0.0/8', '10.0.0.0/25', '::1/128', 'invalid', '169.254.0.0/16', '127.0.0.0/16', '192.0.2.0/24'])
def test_unsafe_or_unusable_pool_rejected(pool):
    with pytest.raises(LocalError):
        MODULE['select_subnets'](pool, [], 2)


def test_network_exhaustion_has_actionable_non_destructive_error():
    with pytest.raises(LocalError, match='no networks were removed'):
        MODULE['select_subnets']('10.69.0.0/16', ['10.0.0.0/8'], 5)


def test_network_declaration_changes_require_review():
    original = plan(config(), [], None)
    changed = config()
    changed['networks']['extra'] = {'name': PROJECT + '_extra'}
    with pytest.raises(LocalError, match='declarations changed'):
        plan(changed, [], None, original)


def test_runner_redacts_logs_and_failure_output_without_masking_exit(tmp_path, capsys):
    runner = object.__new__(MODULE['Platform'])
    runner.state = tmp_path
    secret = 'SYNTHETIC-SERVER-CREDENTIAL-ONLY-TEST'
    runner.values = {'BANKOPS_AGENT_API_TOKEN': secret}
    with pytest.raises(LocalError) as caught:
        runner.run([sys.executable, '-c', 'import sys; print(sys.argv[1]); sys.exit(7)', secret], log='failure.log', show=True)
    assert 'exit 7' in str(caught.value)
    assert secret not in str(caught.value)
    assert secret not in (tmp_path / 'results/failure.log').read_text()
    assert '[REDACTED]' in capsys.readouterr().out


def test_health_reports_migration_failure_even_if_runtime_looks_healthy(capsys):
    runner = object.__new__(MODULE['Platform'])
    states = {name: {'State': 'running', 'Health': 'healthy'} for name in MODULE['RUNTIME']}
    states.update({name: {'State': 'exited', 'ExitCode': 0} for name in MODULE['JOBS']})
    states['migrate']['ExitCode'] = 1
    runner.states = lambda: states
    assert runner.health() is False
    assert 'exit 1' in capsys.readouterr().out


@pytest.mark.parametrize('message, expected', [('port is already allocated', 'localhost port'), ('fully subnetted', 'Network allocation'), ('permission denied', 'Docker access')])
def test_actionable_diagnostics(message, expected):
    assert expected in MODULE['advice'](message)


def test_frontend_supervisor_preserves_failures_even_during_shutdown():
    code = """
import {exitStatus} from './frontend/serve.mjs';
const cases = [
 [0,null,'SIGTERM',0], [143,null,'SIGTERM',0], [null,'SIGTERM','SIGTERM',0],
 [1,null,'SIGTERM',1], [7,null,'SIGTERM',7], [null,'SIGKILL','SIGTERM',137],
 [143,null,undefined,143], [1,null,undefined,1], [0,null,undefined,0],
];
for (const [code,signal,requested,expected] of cases) {
 if (exitStatus(code,signal,requested)!==expected) process.exit(1);
}
"""
    result = subprocess.run(['node', '--input-type=module', '-e', code], cwd=ROOT.parent, capture_output=True)
    assert result.returncode == 0


def test_launcher_does_not_inherit_service_or_build_secrets(monkeypatch):
    for name in ('BANKOPS_DB_PASSWORD', 'VITE_API_TOKEN', 'SPRING_PROFILES_ACTIVE', 'OTEL_EXPORTER_OTLP_HEADERS', 'AIRFLOW__DATABASE__SQL_ALCHEMY_CONN', 'COMPOSE_PROJECT_NAME'):
        monkeypatch.setenv(name, 'synthetic-secret')
    monkeypatch.setenv('DOCKER_CONFIG', 'local-docker-config')
    environment = MODULE['local_environment']()
    assert not any(k.startswith(('BANKOPS_', 'VITE_', 'SPRING_', 'OTEL_', 'AIRFLOW__', 'COMPOSE_')) for k in environment)
    assert environment['DOCKER_CONFIG'] == 'local-docker-config'


@pytest.mark.parametrize('endpoint, allowed', [
    ('npipe:////./pipe/dockerDesktopLinuxEngine', True), ('unix:///var/run/docker.sock', True),
    ('tcp://127.0.0.1:2375', True), ('tcp://[::1]:2375', True),
    ('ssh://remote.example', False), ('tcp://10.1.1.1:2376', False), ('https://remote.example', False),
])
def test_only_local_docker_endpoints_are_allowed(endpoint, allowed):
    assert MODULE['local_endpoint'](endpoint) is allowed
