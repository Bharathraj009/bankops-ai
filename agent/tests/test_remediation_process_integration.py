"""Actual agent process + actual local HTTP evidence sources; no SDK mock transport."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from bankops_agent.evidence.prometheus import DETECTION_QUERIES
from test_approval_process_integration import service
from test_detection import HEALTHY
from test_jaeger import make_span, payload

HEALTH = "CHECK_SERVICE_HEALTH"
REFRESH = "REFRESH_INCIDENT_EVIDENCE"


@contextmanager
def evidence_server():
    class Server(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 32
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with self.server.lock:
                mode = self.server.mode
                self.server.requests.append((self.command, urlsplit(self.path).path, self.headers.get('Authorization')))
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            if mode == "timeout": time.sleep(3)
            code = 503 if mode == "unavailable" or (mode == "partial" and parts.path == "/api/v3/traces") else 200
            if parts.path == "/api/v1/query":
                name = next(name for name, _, expression in DETECTION_QUERIES if expression == query['query'][0])
                value = 0 if mode == "down" and name == "banking_availability" else HEALTHY[name]
                body = {"status":"success","data":{"resultType":"vector","result":[
                    {"metric":{},"value":[float(query['time'][0]),str(value)]}]}}
            elif parts.path == "/api/v3/traces":
                body = payload([make_span(datetime.fromisoformat(query['query.start_time_max'][0]), name="http.request", duration=0.2)])
            else:
                code, body = 404, {}
            data = json.dumps(body if code == 200 else {}).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
        def log_message(self, *args): pass
    server = Server(("127.0.0.1", 0), Handler)
    server.lock, server.mode, server.requests = threading.Lock(), "healthy", []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try: yield server, "http://127.0.0.1:" + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_remediation_real_http_restart_and_failure_verification(tmp_path):
    proposer, reviewer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    proposer_auth, reviewer_auth = {"Authorization":"Bearer " + proposer}, {"Authorization":"Bearer " + reviewer}
    logs = tmp_path / "synthetic.jsonl"
    logs.write_text(json.dumps({"@timestamp": datetime.now(UTC).isoformat(), "service":{"name":"banking-service"},
        "log":{"level":"WARN","logger":"com.bankops.banking.observability.SafeEventLogger"},
        "event_type":"http_request_completed"}) + "\n", encoding="utf-8")
    outcomes, persisted = {}, []
    with evidence_server() as (evidence, evidence_url):
        with service(tmp_path, proposer, reviewer, remediation=evidence_url) as (client, url):
            base = url + "/remediation/proposals"
            def create(action=HEALTH, decision="approve"):
                result = client.post(base, json={"action":action,"evidence_references":["rule.banking_unavailable"]}, headers=proposer_auth)
                assert result.status_code == 201
                path = base + "/" + result.json()['proposal_id']
                if decision:
                    assert client.post(path + "/" + decision, json={"reason":"reviewed_evidence"}, headers=reviewer_auth).status_code == 200
                return path
            def execute(path, action=HEALTH, headers=reviewer_auth, parameters=None):
                return client.post(path + "/execute", json={"action":action,"parameters":parameters or {"service":"banking-service"}}, headers=headers)
            for decision in (None, "reject"):
                assert execute(create(decision=decision)).status_code == 409
            path = create()
            assert execute(path, headers={}).status_code == 401
            assert execute(path, headers=proposer_auth).status_code == 403
            assert execute(path, action=REFRESH).status_code == 409
            assert execute(path, parameters={"service":"http://arbitrary.invalid"}).status_code == 400
            assert execute(path, parameters={"service":"banking-service","command":"shell"}).status_code == 400
            assert client.patch(path, json={"action":REFRESH}, headers=reviewer_auth).status_code == 405
            assert not evidence.requests
            first = execute(path)
            assert first.status_code == 200 and first.json()['outcome'] == "service_up"
            persisted.append(first.json())
            outcomes['health'] = first.json()['outcome']
            assert len(evidence.requests) == 7
            assert execute(path).status_code == 409 and len(evidence.requests) == 7
            second = execute(create(REFRESH), action=REFRESH)
            assert second.status_code == 200 and second.json()['outcome'] == "evidence_refreshed"
            persisted.append(second.json())
            outcomes['refresh'] = second.json()['outcome']
            assert len(evidence.requests) == 15
            race = create()
            before = len(evidence.requests)
            with ThreadPoolExecutor(max_workers=2) as pool:
                codes = sorted(pool.map(lambda _: execute(race).status_code, range(2)))
            assert codes == [200,409] and len(evidence.requests)-before == 7
            persisted.append(client.get(race + "/execution", headers=reviewer_auth).json())
            outcomes['concurrent'] = codes
        with service(tmp_path, proposer, reviewer, remediation=evidence_url) as (client, url):
            base = url + "/remediation/proposals"
            for original in persisted:
                path = base + "/" + original['proposal_id']
                assert client.get(path + "/execution", headers=reviewer_auth).json() == original
                assert execute(path, action=original['action']).status_code == 409
            outcomes['restart_persistence'] = True
            for mode, action, status, outcome in (
                ("down", HEALTH, "SUCCEEDED", "service_down"),
                ("partial", REFRESH, "SUCCEEDED", "evidence_partial"),
                ("unavailable", REFRESH, "FAILED", "source_unavailable"),
                ("timeout", HEALTH, "FAILED", "timeout"),
            ):
                evidence.mode = mode
                if mode == 'unavailable': logs.unlink()
                path = create(action)
                before = len(evidence.requests)
                response = execute(path, action=action)
                assert response.status_code == 200
                result = response.json()
                assert result['status'] == status and result['outcome'] == outcome
                persisted.append(result)
                expected = 8 if action == REFRESH else 7
                assert len(evidence.requests)-before == expected
                recorded = len(evidence.requests)
                assert execute(path, action=action).status_code == 409
                time.sleep(0.1)
                assert len(evidence.requests) == recorded
                outcomes[mode] = outcome
            assert all(method == 'GET' and path in ('/api/v1/query','/api/v3/traces') and auth is None
                       for method,path,auth in evidence.requests)
            outcomes['read_only_http_requests'] = len(evidence.requests)
        with service(tmp_path, proposer, reviewer, remediation=evidence_url) as (client, url):
            before = len(evidence.requests)
            verified = []
            for original in persisted:
                path = url + '/remediation/proposals/' + original['proposal_id']
                assert client.get(path + '/execution', headers=reviewer_auth).json() == original
                assert client.post(path + '/execute', json={'action':original['action'],
                    'parameters':{'service':'banking-service'}}, headers=reviewer_auth).status_code == 409
                response = client.post(path + '/verify', json={'basis':'recorded_execution'}, headers=reviewer_auth)
                assert response.status_code == 201
                record = response.json()
                assert record['status'] == ('EXECUTION_SUCCEEDED' if original['status'] == 'SUCCEEDED' else 'EXECUTION_FAILED')
                assert record['incident_resolution'] == 'NOT_DETERMINED'
                verified.append(record)
                assert client.get(path + '/execution', headers=reviewer_auth).json() == original
            assert len(evidence.requests) == before
            outcomes['failed_execution_restart_persistence'] = True
        with service(tmp_path, proposer, reviewer, remediation=evidence_url) as (client, url):
            for record in verified:
                path = url + '/remediation/proposals/' + record['proposal_id']
                assert client.get(path + '/verification', headers=proposer_auth).json() == record
                assert client.post(path + '/verify', json={'basis':'recorded_execution'}, headers=reviewer_auth).status_code == 409
            assert len(evidence.requests) == before
            outcomes['verification_restart_persistence'] = True
    for item in persisted:
        assert [event['event'] for event in item['audit']] == ['RUNNING',item['status']]
        assert item['audit'][0]['timestamp'] == item['started_at']
        assert item['audit'][1]['timestamp'] == item['completed_at']
        assert datetime.fromisoformat(item['completed_at']) >= datetime.fromisoformat(item['started_at'])
    with sqlite3.connect(tmp_path / 'approvals.sqlite3') as database:
        assert database.execute('SELECT count(*) FROM remediation_executions').fetchone()[0] == 7
        assert database.execute('SELECT count(*) FROM execution_audit').fetchone()[0] == 14
        assert database.execute('SELECT count(*) FROM execution_verifications').fetchone()[0] == 7
        assert database.execute('SELECT count(*) FROM verification_audit').fetchone()[0] == 7
        for statement in ('DELETE FROM execution_audit', "UPDATE execution_audit SET event='FAILED'"):
            with pytest.raises(sqlite3.IntegrityError): database.execute(statement)
        assert database.execute('SELECT count(*) FROM execution_audit').fetchone()[0] == 14
    assert not (tmp_path / 'forbidden-attempt.log').exists()
    outcomes['execution_records'], outcomes['audit_records'] = 7,14
    print('REMEDIATION_PROCESS_VERIFICATION=' + json.dumps(outcomes,sort_keys=True))
