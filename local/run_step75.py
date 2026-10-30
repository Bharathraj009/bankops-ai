"""Disposable real scheduler -> agent -> RAG -> Chromium verification, no banking writes.

Reuses the isolated project generator, preserves all volumes and existing services.
Only the fixture DAG schedule/retries are accelerated; production DAG is untouched.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import secrets
import socket
import subprocess
import time
import urllib.request
import urllib.error

from recovery import Recovery, wait_for

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'local/results/step75'
OUT.mkdir(parents=True, exist_ok=True)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(port, path, method='GET', body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', method=method,
        data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        response = OPENER.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    data = response.read()
    try:
        value = json.loads(data)
    except ValueError:
        value = None
    return response.status, value


def main():
    for port in (15268, 18068, 19068, 13068, 16668):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    fixture = Recovery()
    report = {'project': fixture.project, 'directory': str(fixture.directory),
              'started_at': datetime.now(timezone.utc).isoformat(), 'real_inference': False}
    (OUT / 'current.json').write_text(json.dumps(report))
    path = fixture.directory / 'compose.json'
    def save():
        path.write_text(json.dumps(fixture.config))
        (OUT / 'report.json').write_text(json.dumps(report, indent=2))
    try:
        config = fixture.config
        for name, image in {'agent': 'bankops-step75/agent:local',
                'frontend': 'bankops-step75/frontend:local',
                'airflow': 'bankops-step71-remediation/airflow:final',
                'jaeger': 'bankops-step72c/jaeger:verified'}.items():
            config['services'][name]['image'] = image
        banking = config['services']['banking']
        # Preserve native SafeLogFilter output verbatim in a shared evidence file.
        # Fixture-only shell tee; no fabricated events or customer operations.
        banking['entrypoint'] = ['sh', '-c', 'java -jar /app/banking.jar | tee /native/banking.jsonl']
        banking['environment'].update(BANKOPS_DEV_RESERVE_BOOTSTRAP_ENABLED='false',
            LOGGING_FILE_NAME='/native/banking.jsonl', LOGGING_STRUCTURED_FORMAT_FILE='ecs')
        volume = fixture.project + '_native'
        config['volumes']['native'] = {'name': volume}
        banking.setdefault('volumes', []).append({'type': 'volume', 'source': 'native', 'target': '/native'})
        config['services']['native-init'] = {'image': 'postgres:17', 'user': '0',
            'entrypoint': ['sh', '-c', 'chown 10001:10001 /native && chmod 750 /native'],
            'network_mode': 'none', 'volumes': [{'type': 'volume', 'source': 'native', 'target': '/native'}]}
        banking['depends_on']['native-init'] = {'condition': 'service_completed_successfully'}
        config['services']['postgres']['healthcheck']['test'] = ['CMD-SHELL', 'pg_isready -U bankops -d bankops']
        # Finance/metadata/telemetry remain internal. Keep the generated web/API
        # bridges publishable for Windows localhost access, as in the base fixture.
        agent = config['services']['agent']
        agent['networks']['interfaces'] = None
        agent['environment'].update(BANKOPS_AGENT_RAG_ENABLED='true', BANKOPS_AGENT_LOG_INCLUDE_INFO='true',
            BANKOPS_AGENT_LOG_SOURCE_DIRECTORY='/native', BANKOPS_AGENT_LOG_WINDOW_SECONDS='1800',
            BANKOPS_AGENT_AIRFLOW_ENABLED='false', BANKOPS_AGENT_AIRFLOW_URL='https://airflow-evidence:8443',
            BANKOPS_AGENT_AIRFLOW_CA_FILE='/step75-ca/cert.pem',
            BANKOPS_AGENT_LLM_EXTERNAL_OPT_IN='false', BANKOPS_AGENT_LLM_PROVIDER='disabled')
        agent.setdefault('volumes', []).append({'type': 'volume', 'source': 'native', 'target': '/native', 'read_only': True})
        tls = fixture.directory / 'tls'
        tls.mkdir()
        certificate = subprocess.run(['C:/Program Files/Git/usr/bin/openssl.exe', 'req', '-x509', '-newkey', 'rsa:2048',
            '-nodes', '-keyout', str(tls / 'key.pem'), '-out', str(tls / 'cert.pem'), '-days', '1',
            '-subj', '/CN=airflow-evidence', '-addext', 'subjectAltName=DNS:airflow-evidence'], capture_output=True)
        assert certificate.returncode == 0
        agent['volumes'].append({'type': 'bind', 'source': str(tls / 'cert.pem'), 'target': '/step75-ca/cert.pem', 'read_only': True})
        config['services']['airflow-evidence'] = {'image': 'bankops-step75/agent:local',
            'entrypoint': ['python', '/step75/proxy.py'], 'networks': ['interfaces'],
            'volumes': [{'type': 'bind', 'source': str(tls), 'target': '/tls', 'read_only': True},
                {'type': 'bind', 'source': str(ROOT / 'local/airflow_tls_proxy.py'), 'target': '/step75/proxy.py', 'read_only': True}]}
        # Actual tasks run with a deliberately unavailable read-only schema-history
        # permission. Bank records and the cluster authentication policy are untouched.
        dagdir = fixture.directory / 'dags'
        dagdir.mkdir()
        dagtext = (ROOT / 'airflow/dags/bankops_reconciliation.py').read_text()
        assert "schedule='0 0 * * *'" in dagtext and "'retries':2" in dagtext
        dagtext = dagtext.replace("schedule='0 0 * * *'", "schedule='* * * * *'").replace("'retries':2", "'retries':0")
        (dagdir / 'bankops_reconciliation.py').write_text(dagtext)
        wrapper = fixture.directory / 'airflow-start.py'
        wrapper.write_text("import os,runpy,psycopg\n"
            "runpy.run_path('/opt/bankops/start.py')['configure']()\n"
            "os.execvp('airflow',['airflow','standalone'])\n")
        airflow = config['services']['airflow']
        airflow['command'] = ['python', '/step75/start.py']
        airflow['environment'].update(AIRFLOW__DAG_PROCESSOR__MIN_FILE_PROCESS_INTERVAL='5',
            AIRFLOW__SCHEDULER__SCHEDULER_HEARTBEAT_SEC='2')
        airflow.setdefault('volumes', []).extend([
            {'type': 'bind', 'source': str(dagdir), 'target': '/opt/airflow/dags', 'read_only': True},
            {'type': 'bind', 'source': str(wrapper), 'target': '/step75/start.py', 'read_only': True}])
        save()
        print('Starting disposable Compose project ' + fixture.project, flush=True)
        fixture.dc('up', '-d', '--wait', '--wait-timeout', '600', 'frontend', 'airflow', 'airflow-evidence', log='startup.log', timeout=720)
        # Bootstrap disabled: no banking records should exist in this new fixture.
        snapshot = fixture.snapshot()
        assert snapshot['counts'] == [0, 0, 0]
        # Generate a native read-only API outcome; never create an account/transfer.
        fixture.api('/api/v1/operator/me')
        report['banking_snapshot_before'] = snapshot
        fixture.dc('exec', '-T', 'postgres', 'sh', '-c',
            'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U bankops -d bankops -v ON_ERROR_STOP=1 -c "REVOKE SELECT ON public.flyway_schema_history FROM bankops_reconciliation"', log='read-only-source-fault.log')
        status, value = http(18068, '/auth/token', 'POST', {'username': 'localadmin', 'password': fixture.values['BANKOPS_AIRFLOW_UI_PASSWORD']})
        assert status in (200, 201)
        admin = value['access_token']
        status, value = http(18068, '/auth/token', 'POST', {'username': 'agentviewer', 'password': fixture.values['BANKOPS_AIRFLOW_VIEWER_PASSWORD']})
        assert status in (200, 201)
        viewer = value['access_token']
        assert http(18068, '/api/v2/config', token=viewer)[0] == 403
        dag = '/api/v2/dags/bankops_daily_reconciliation'
        assert http(18068, dag, token=viewer)[0] == 200
        agent['environment'].update(BANKOPS_AGENT_AIRFLOW_ENABLED='true', BANKOPS_AGENT_AIRFLOW_API_TOKEN=viewer)
        save()
        fixture.dc('up', '-d', '--no-deps', '--wait', 'agent', log='agent-airflow-connect.log')
        print('Agent connected with viewer credential; unpausing accelerated scheduled DAG', flush=True)
        assert http(18068, dag, 'PATCH', {'is_paused': False}, admin)[0] == 200
        def completed():
            status, value = http(18068, dag + '/dagRuns?limit=10&order_by=-run_after', token=viewer)
            assert status == 200
            runs = [row for row in value['dag_runs'] if row.get('state') == 'failed' and row.get('run_type') == 'scheduled']
            return runs[0] if runs else None
        run = wait_for(completed, 360)
        assert http(18068, dag, 'PATCH', {'is_paused': True}, admin)[0] == 200
        status, tasks = http(18068, dag + '/dagRuns/' + run['dag_run_id'] + '/taskInstances', token=viewer)
        assert status == 200 and len(tasks['task_instances']) == 4
        report['scheduler'] = {'run_id': run['dag_run_id'], 'run_type': run['run_type'], 'state': run['state'],
            'logical_date': run.get('logical_date'), 'started_at': run.get('start_date'), 'ended_at': run.get('end_date'),
            'tasks': [{'id': task['task_id'], 'state': task['state']} for task in tasks['task_instances']],
            'accelerated_fixture_schedule': '* * * * *', 'manual_dag_trigger_posts': 0}
        save()
        status, investigation = http(15268, '/investigation-api/workflows/investigate', 'POST')
        report['investigation'] = investigation
        save()
        assert status == 200
        assert 'reconciliation_insufficient_data' in investigation['detection']['triggered_rules']
        assert investigation['detection']['airflow']['runs'][0]['summary_status'] == 'INSUFFICIENT_DATA'
        assert investigation['rca']['retrieval']['status'] == 'matched'
        assert any(s['document_id'] == 'reconciliation' for s in investigation['rca']['retrieval']['sources'])
        assert investigation['rca']['reason'] == 'disabled'
        assert investigation['logs']['status'] == 'ok' and any(e['level'] == 'INFO' for e in investigation['logs']['events'])
        report['investigation'] = investigation
        print('Actual scheduled failure reached LangGraph, native logs and RAG; verifying Chromium', flush=True)
        result = subprocess.run(['node', str(ROOT / 'local/step75_browser.mjs')], cwd=ROOT,
            input=json.dumps({'base': 'http://127.0.0.1:15268'}), text=True, capture_output=True, timeout=180)
        (fixture.directory / 'browser.log').write_text(result.stderr)
        assert result.returncode == 0, 'Chromium verification failed; inspect browser.log'
        report['browser'] = json.loads(result.stdout)
        fixture.dc('exec', '-T', 'postgres', 'sh', '-c',
            'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U bankops -d bankops -v ON_ERROR_STOP=1 -c "GRANT SELECT ON public.flyway_schema_history TO bankops_reconciliation"', log='read-only-source-restored.log')
        assert fixture.snapshot() == snapshot
        assert fixture.migration_hashes() == fixture.baseline_hashes
        report.update(status='PASS', banking_snapshot_unchanged=True, migrations_unchanged=True,
            native_info_ingested=True, viewer_config_denied=True, cloud_requests=0)
        save()
        print('Step75 scheduler-to-dashboard PASS', flush=True)
    except BaseException as error:
        report.update(status='FAILED', failure_type=type(error).__name__)
        save()
        raise
    finally:
        fixture.dc('down', '--timeout', '30', log='cleanup.log', timeout=240)
        report['fixture_removed_volumes_preserved'] = True
        save()


if __name__ == '__main__':
    main()
