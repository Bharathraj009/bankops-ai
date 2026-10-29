"""End-to-end audit boundaries, lost completion writes and restart safety."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import secrets
import sqlite3

import pytest

from test_approval_process_integration import service
from test_remediation_process_integration import evidence_server, HEALTH, REFRESH


def test_lifecycle_audit_failure_boundaries_and_restarts(tmp_path):
    proposer, reviewer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    pa, ra = {'Authorization':'Bearer ' + proposer}, {'Authorization':'Bearer ' + reviewer}
    decision = {'reason':'reviewed_evidence'}
    verification = {'basis':'recorded_execution'}
    database = tmp_path / 'approvals.sqlite3'
    records = {}
    with evidence_server() as (source, evidence_url):
        with service(tmp_path, proposer, reviewer, remediation=evidence_url) as (client, url):
            base = url + '/remediation/proposals'
            def create(action=HEALTH):
                response = client.post(base, json={'action':action,'evidence_references':['rule.banking_unavailable']}, headers=pa)
                assert response.status_code == 201
                assert response.json()['status'] == 'PENDING'
                return response.json()['proposal_id']
            def post(identifier, suffix, body, headers=ra):
                return client.post(base + '/' + identifier + suffix, json=body, headers=headers)
            def action_body(action=HEALTH):
                return {'action':action,'parameters':{'service':'banking-service'}}
            rejected = create()
            assert post(rejected, '/reject', decision).status_code == 200
            assert post(rejected, '/approve', decision).status_code == 409
            assert post(rejected, '/execute', action_body()).status_code == 409
            assert post(rejected, '/verify', verification).status_code == 404
            for action in (HEALTH, REFRESH):
                identifier = create(action)
                assert post(identifier, '/execute', action_body(action)).status_code == 409
                assert post(identifier, '/verify', verification).status_code == 404
                assert post(identifier, '/approve', decision, pa).status_code == 403
                assert post(identifier, '/approve', decision, {}).status_code == 401
                with ThreadPoolExecutor(max_workers=3) as pool:
                    assert sorted(pool.map(lambda _: post(identifier,'/approve',decision).status_code,range(3))) == [200,409,409]
                assert post(identifier, '/reject', decision).status_code == 409
                assert post(identifier, '/execute', action_body(action), pa).status_code == 403
                with ThreadPoolExecutor(max_workers=3) as pool:
                    assert sorted(pool.map(lambda _: post(identifier,'/execute',action_body(action)).status_code,range(3))) == [200,409,409]
                original = client.get(base + '/' + identifier + '/execution', headers=ra).json()
                assert original['status'] == 'SUCCEEDED'
                assert post(identifier, '/verify', verification, pa).status_code == 403
                assert post(identifier, '/verify', verification, {}).status_code == 401
                # Failure after execution but before verification commit must not alter history.
                with sqlite3.connect(database) as conn:
                    conn.execute("CREATE TRIGGER injected_verification_failure BEFORE INSERT ON verification_audit BEGIN SELECT RAISE(ABORT,'synthetic'); END")
                assert post(identifier, '/verify', verification).status_code == 503
                assert client.get(base + '/' + identifier + '/verification', headers=ra).status_code == 404
                assert client.get(base + '/' + identifier + '/execution', headers=ra).json() == original
                with sqlite3.connect(database) as conn:
                    conn.execute('DROP TRIGGER injected_verification_failure')
                records[identifier] = original
            incomplete = create()
            assert post(incomplete, '/approve', decision).status_code == 200
            # Simulate storage failure after dispatch, before terminal execution/audit commit.
            with sqlite3.connect(database) as conn:
                conn.execute("CREATE TRIGGER injected_completion_failure BEFORE INSERT ON execution_audit WHEN NEW.event!='RUNNING' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
            assert post(incomplete, '/execute', action_body()).status_code == 503
            original = client.get(base + '/' + incomplete + '/execution', headers=ra).json()
            assert original['status'] == 'RUNNING' and original['outcome'] is None
            assert [a['event'] for a in original['audit']] == ['RUNNING']
            records[incomplete] = original
            with sqlite3.connect(database) as conn:
                conn.execute('DROP TRIGGER injected_completion_failure')
            before = len(source.requests)
            assert before == 22  # 7 health + 8 evidence + 7 lost completion
        verified = {}
        with service(tmp_path, proposer, reviewer, remediation=evidence_url) as (client, url):
            for identifier, original in records.items():
                path = url + '/remediation/proposals/' + identifier
                assert client.get(path + '/execution', headers=ra).json() == original
                assert client.post(path + '/execute',json=action_body(original['action']),headers=ra).status_code == 409
                with ThreadPoolExecutor(max_workers=3) as pool:
                    responses = list(pool.map(lambda _: client.post(path + '/verify',json=verification,headers=ra),range(3)))
                assert sorted(r.status_code for r in responses) == [201,409,409]
                record = next(r.json() for r in responses if r.status_code == 201)
                assert record['status'] == ('VERIFICATION_INCONCLUSIVE' if identifier == incomplete else 'EXECUTION_SUCCEEDED')
                assert record['incident_resolution'] == 'NOT_DETERMINED'
                verified[identifier] = record
            assert len(source.requests) == before
        # Recover records with execution disabled and no allowed outbound connections.
        with service(tmp_path, proposer, reviewer) as (client, url):
            for identifier, original in records.items():
                path = url + '/remediation/proposals/' + identifier
                assert client.get(path,headers=pa).json()['status'] == 'APPROVED'
                assert client.get(path + '/execution',headers=ra).json() == original
                assert client.get(path + '/verification',headers=pa).json() == verified[identifier]
                assert client.post(path + '/verify',json=verification,headers=ra).status_code == 409
                assert client.post(path + '/execute',json=action_body(original['action']),headers=ra).status_code == 503
            assert len(source.requests) == before
    with sqlite3.connect(database) as conn:
        for table in ('read_only_proposals','read_only_audit','approval_bindings','remediation_executions','execution_audit','execution_verifications','verification_audit'):
            for statement in (f'DELETE FROM {table}',f'UPDATE {table} SET rowid=rowid'):
                with pytest.raises(sqlite3.IntegrityError): conn.execute(statement)
        assert conn.execute('SELECT count(*) FROM execution_verifications').fetchone()[0] == 3
        assert conn.execute('SELECT count(*) FROM verification_audit').fetchone()[0] == 3
        assert conn.execute('SELECT count(*) FROM execution_audit').fetchone()[0] == 5
        for identifier in records:
            approval = conn.execute('SELECT timestamp FROM read_only_audit WHERE proposal_id=? ORDER BY sequence',(identifier,)).fetchall()
            execution = records[identifier]
            times = [datetime.fromisoformat(a[0]) for a in approval] + [datetime.fromisoformat(a['timestamp']) for a in execution['audit']] + [datetime.fromisoformat(verified[identifier]['verified_at'])]
            assert times == sorted(times)
    assert not (tmp_path / 'forbidden-attempt.log').exists()
    print('RELIABILITY_VERIFICATION=3 executions; 3 verifications; 22 read-only source requests; no retries; persisted across 3 processes')
