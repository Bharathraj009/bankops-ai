from concurrent.futures import ThreadPoolExecutor
import sqlite3
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

from bankops_agent.app import create_app
from bankops_agent.remediation.execution_store import ExecutionStore
from bankops_agent.remediation.models import ExecutionRequest
from bankops_agent.remediation.verification import VerificationStore, AlreadyVerified
from test_execution import environment, proposal, request, HEALTH, REFRESH
from test_approvals import setup

BODY = {'basis': 'recorded_execution'}


@pytest.mark.parametrize('action,outcome,status', [
    (HEALTH,'service_up','EXECUTION_SUCCEEDED'),
    (HEALTH,'service_down','EXECUTION_SUCCEEDED'),
    (REFRESH,'evidence_refreshed','EXECUTION_SUCCEEDED'),
    (REFRESH,'evidence_partial','EXECUTION_SUCCEEDED'),
    *[(HEALTH,o,'EXECUTION_FAILED') for o in ('timeout','cancelled','source_unavailable','internal_failure')],
    (HEALTH,None,'VERIFICATION_INCONCLUSIVE'),
    (HEALTH,'evidence_partial','VERIFICATION_INCONCLUSIVE'),
    (REFRESH,'service_up','VERIFICATION_INCONCLUSIVE')])
def test_recorded_outcomes(environment, action, outcome, status):
    settings, app, client, proposer, reviewer, sources = environment
    path = proposal(environment, action)
    identifier = UUID(path.split('/')[-1])
    executions = ExecutionStore(app.app.state.approval_store)
    executions.claim(identifier, ExecutionRequest.model_validate(request(action)))
    if outcome:
        executions.finish(identifier, 'FAILED' if status == 'EXECUTION_FAILED' else 'SUCCEEDED', outcome)
    original = client.get(path + '/execution', headers=reviewer).json()
    result = client.post(path + '/verify', json=BODY, headers=reviewer)
    assert result.status_code == 201, result.text
    record = result.json()
    assert record['status'] == status
    assert record['incident_resolution'] == 'NOT_DETERMINED'
    assert len(record['execution_sha256']) == 64
    assert record['verified_at'] >= original['started_at']
    assert client.get(path + '/execution', headers=reviewer).json() == original
    assert client.post(path + '/verify', json=BODY, headers=reviewer).status_code == 409
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path + '/verification', headers=proposer).json() == record
        assert restarted.post(path + '/verify', json=BODY, headers=reviewer).status_code == 409
    assert sources.prometheus_collector.calls == sources.jaeger_collector.calls == sources.log_collector.calls == 0


def test_auth_missing_invalid_and_no_fresh_evidence(environment):
    _, _, client, proposer, reviewer, sources = environment
    path = proposal(environment)
    assert client.post(path + '/verify', json=BODY).status_code == 401
    assert client.post(path + '/verify', json=BODY, headers=proposer).status_code == 403
    assert client.post(path + '/verify', json=BODY, headers=reviewer).status_code == 404
    assert client.get(path + '/verification', headers=reviewer).status_code == 404
    assert client.post('/remediation/proposals/invalid/verify', json=BODY, headers=reviewer).status_code == 400
    assert client.post(f'/remediation/proposals/{uuid4()}/verify', json=BODY, headers=reviewer).status_code == 404
    for body in ({}, BODY | {'collect_fresh_evidence': True}, {'basis': 'https://private'}, BODY | {'command':'private'}):
        assert client.post(path + '/verify', json=body, headers=reviewer).status_code == 400
    assert sources.prometheus_collector.calls == 0


def test_concurrency_atomic_immutable_and_rollback(environment):
    settings, app, client, _, reviewer, _ = environment
    path = proposal(environment)
    assert client.post(path + '/execute', json=request(), headers=reviewer).status_code == 200
    identifier = UUID(path.split('/')[-1])
    approvals = app.app.state.approval_store
    with approvals.connection() as connection:
        connection.execute("CREATE TRIGGER fail_verification BEFORE INSERT ON verification_audit BEGIN SELECT RAISE(ABORT,'test'); END")
    assert client.post(path + '/verify', json=BODY, headers=reviewer).status_code == 503
    assert client.get(path + '/verification', headers=reviewer).status_code == 404
    with approvals.connection() as connection:
        connection.execute('DROP TRIGGER fail_verification')
    def verify(_):
        from bankops_agent.remediation.store import ApprovalStore
        try:
            VerificationStore(ApprovalStore(settings.approval_db_path)).create(identifier)
            return 201
        except AlreadyVerified:
            return 409
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(verify, range(4))) == [201,409,409,409]
    record = client.get(path + '/verification', headers=reviewer).json()
    with approvals.connection() as connection:
        audit = connection.execute('SELECT * FROM verification_audit').fetchall()
        assert len(audit) == 1 and audit[0]['event'] == 'VERIFIED'
        from datetime import datetime
        assert datetime.fromisoformat(audit[0]['timestamp']) == datetime.fromisoformat(record['verified_at'])
        for table in ('execution_verifications','verification_audit'):
            for sql in (f'DELETE FROM {table}', f'UPDATE {table} SET proposal_id=proposal_id'):
                with pytest.raises(sqlite3.IntegrityError): connection.execute(sql)


def test_modified_binding_is_inconclusive(environment):
    _, app, client, _, reviewer, _ = environment
    path = proposal(environment)
    client.post(path + '/execute', json=request(), headers=reviewer)
    with app.app.state.approval_store.connection() as connection:
        connection.execute('DROP TRIGGER binding_no_update')
        connection.execute("UPDATE approval_bindings SET fingerprint=?", ('0'*64,))
    result = client.post(path + '/verify', json=BODY, headers=reviewer)
    assert result.status_code == 201
    assert result.json()['reason'] == 'inconsistent_record'


def test_disabled_defaults(setup):
    from bankops_agent.config import Settings
    assert not Settings(environment='production').remediation_enabled
    with TestClient(create_app(Settings())) as client:
        assert client.post(f'/remediation/proposals/{uuid4()}/verify', json=BODY).status_code == 503


def test_recorded_verification_when_execution_disabled_and_later_finish(environment):
    from bankops_agent.config import Settings
    settings, app, client, _, reviewer, _ = environment
    path = proposal(environment)
    identifier = UUID(path.split('/')[-1])
    store = ExecutionStore(app.app.state.approval_store)
    store.claim(identifier, ExecutionRequest.model_validate(request()))
    disabled = Settings(**(settings.model_dump() | {'remediation_enabled':False}))
    with TestClient(create_app(disabled)) as restarted:
        result = restarted.post(path + '/verify', json=BODY, headers=reviewer)
        assert result.status_code == 201
        assert result.json()['status'] == 'VERIFICATION_INCONCLUSIVE'
        store.finish(identifier, 'SUCCEEDED', 'service_up')
        assert restarted.get(path + '/verification', headers=reviewer).json() == result.json()
        assert restarted.post(path + '/execute', json=request(), headers=reviewer).status_code == 503


def test_storage_failure_safe_no_partial_records(environment, monkeypatch):
    _, app, client, _, reviewer, sources = environment
    path = proposal(environment)
    client.post(path + '/execute', json=request(), headers=reviewer)
    from contextlib import contextmanager
    @contextmanager
    def locked():
        raise sqlite3.OperationalError('PRIVATE path credentials')
        yield
    with monkeypatch.context() as patch:
        patch.setattr(app.app.state.approval_store, 'connection', locked)
        response = client.post(path + '/verify', json=BODY, headers=reviewer)
        assert response.status_code == 503 and 'PRIVATE' not in response.text
    assert client.get(path + '/verification', headers=reviewer).status_code == 404
    assert sources.prometheus_collector.calls == 1
