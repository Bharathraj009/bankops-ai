"""Opt-in Chromium integration; isolated sources, real HTTP agent/proxy, mock AI."""
from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time

import httpx2 as httpx
import pytest
import uvicorn

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from test_cloud_rag import response
from test_remediation_process_integration import evidence_server

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.environ.get('BANKOPS_STEP74_BROWSER') != '1', reason='Explicit isolated browser integration opt-in')


@contextmanager
def api_server(app):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, lifespan='off'))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(.05)
        assert server.started
        yield 'http://127.0.0.1:' + str(listener.getsockname()[1])
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


@pytest.mark.parametrize('cloud', [False, True], ids=['http-observability-disabled-inference', 'synthetic-mocked-cloud'])
def test_browser_agent_graph_rag_and_approval_boundaries(tmp_path, monkeypatch, cloud):
    import bankops_agent.app as app_module
    from bankops_agent.rca.provider import create_provider
    token, proposer, reviewer = (secrets.token_urlsafe(32) for _ in range(3))
    digest = lambda value: hashlib.sha256(value.encode()).hexdigest()
    seen = []
    monkeypatch.setattr(app_module, 'create_provider', lambda settings: create_provider(settings,
        transport=httpx.MockTransport(lambda request: seen.append(request) or response(request))))
    # Prevent ambient provider credentials/settings from influencing this fixture.
    for key in list(os.environ):
        if key.startswith(('BANKOPS_', 'LANGSMITH_', 'OPENAI_', 'GROQ_')):
            monkeypatch.delenv(key)
    (tmp_path / 'banking.jsonl').write_text(json.dumps({'@timestamp': datetime.now(UTC).isoformat(),
        'service': {'name': 'banking-service'},
        'log': {'level': 'WARN', 'logger': 'com.bankops.banking.observability.SafeEventLogger'},
        'event_type': 'http_request_completed'}) + '\n')
    with evidence_server() as (evidence, url):
        evidence.mode = 'down'
        settings = Settings(environment='test', rag_enabled=True,
            evidence_mode='synthetic_demo' if cloud else 'operational', synthetic_scenario='service_down',
            llm_provider='openai_cloud' if cloud else 'disabled', llm_external_opt_in=cloud,
            llm_model='gpt-5-mini', llm_api_key='synthetic-step74-test-only' if cloud else None,
            api_token_sha256=digest(token), approval_db_path=str(tmp_path / 'approvals.sqlite3'),
            approval_proposer_token_sha256=digest(proposer), approval_reviewer_token_sha256=digest(reviewer),
            prometheus_url=url, jaeger_url=url, log_source_directory=str(tmp_path),
            incident_max_evidence_age_seconds=300)
        app = create_app(settings)
        assert set(app.app.state.investigation_workflow.get_graph().nodes) == {
            '__start__', '__end__', 'detection', 'evidence_collection', 'report_assembly', 'rca'}
        with api_server(app) as agent_url:
            with httpx.Client(base_url=agent_url, trust_env=False) as client:
                assert client.post('/workflows/investigate').status_code == 401
                assert client.post('/workflows/investigate', headers={'Authorization': 'Bearer ' + token}, json={'evidence': 'untrusted'}).status_code == 400
                base = '/remediation/proposals'
                proposal = {'action': 'CHECK_SERVICE_HEALTH', 'evidence_references': ['rule.banking_unavailable']}
                pa, ra = {'Authorization': 'Bearer ' + proposer}, {'Authorization': 'Bearer ' + reviewer}
                assert client.post(base, headers=ra, json=proposal).status_code == 403
                created = client.post(base, headers=pa, json=proposal)
                assert created.status_code == 201
                path = base + '/' + created.json()['proposal_id']
                assert client.post(path + '/approve', headers=pa, json={'reason': 'reviewed_evidence'}).status_code == 403
                assert client.post(path + '/approve', headers=ra, json={'reason': 'reviewed_evidence'}).status_code == 200
                assert client.post(path + '/execute', headers=ra, json={'action': 'CHECK_SERVICE_HEALTH', 'parameters': {'service': 'banking-service'}}).status_code == 503
            with socket.socket() as port_socket:
                port_socket.bind(('127.0.0.1', 0))
                port = port_socket.getsockname()[1]
            env = {k: v for k, v in os.environ.items() if not k.startswith(('BANKOPS_', 'VITE_', 'OPENAI_', 'GROQ_'))}
            env.update(BANKOPS_AGENT_API_TOKEN=token, BANKOPS_INVESTIGATION_API_TARGET=agent_url,
                       BANKOPS_MONITORING_API_TARGET=agent_url)
            with (tmp_path / 'vite.log').open('w') as log:
                vite = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', str(port), '--strictPort'], cwd=ROOT / 'frontend', env=env, stdout=log, stderr=log)
                try:
                    base_url = f'http://127.0.0.1:{port}'
                    with httpx.Client(trust_env=False) as client:
                        for _ in range(300):
                            try:
                                if client.get(base_url).status_code == 200:
                                    break
                            except httpx.HTTPError:
                                pass
                            time.sleep(.1)
                        else:
                            pytest.fail('Isolated frontend did not start')
                    browser = subprocess.run(['node', 'local/step74_browser.mjs'], cwd=ROOT,
                        input=json.dumps({'base': base_url, 'cloud': cloud}), text=True, capture_output=True, timeout=180)
                    assert browser.returncode == 0, browser.stderr
                    results = json.loads(browser.stdout)
                    assert len(results) == 2
                    assert len(seen) == (2 if cloud else 0)
                    assert bool(evidence.requests) is not cloud
                    for item in results:
                        assert item['report']['traces']['status'] == 'ok'
                        assert item['report']['logs']['status'] == 'ok'
                    out = ROOT / 'local/results/step74'
                    out.mkdir(parents=True, exist_ok=True)
                    (out / ('cloud-browser.json' if cloud else 'http-browser.json')).write_text(json.dumps({
                        'results': results, 'mock_provider_calls': len(seen),
                        'http_evidence_requests': len(evidence.requests), 'real_inference': False}, indent=2))
                finally:
                    vite.terminate()
                    vite.wait(timeout=15)
