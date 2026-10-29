"""Isolated HTTP integration: real agent + authenticated synthetic Airflow v2.

Only loopback sockets; no scheduler, banking database or live monitoring calls.
Viewer credential is generated in memory and is never returned to the browser.
"""
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import secrets
import threading
from urllib.parse import urlsplit

from incident_agent import Metrics, Settings, create_app, uvicorn

TASKS = ('validate_read_only_connectivity', 'execute_reconciliation', 'validate_results', 'execution_summary')
RULES = ('completed_double_entry', 'account_balances', 'ledger_consistency', 'lifecycle_ledger')
BASE = '/api/v2/dags/bankops_daily_reconciliation/dagRuns'


def main():
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    dates = [now-timedelta(hours=i+1) for i in range(5)]
    counters = dict(authenticated_gets=0, unauthorized=0, writes=0)
    class Airflow(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def send(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            counters['writes'] += 1
            self.send(405, {})
        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST
        def do_GET(self):
            path = urlsplit(self.path).path
            # Test-only aggregate diagnostics: no credentials, IDs or raw records.
            if path == '/fixture-status':
                return self.send(200, counters)
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+token):
                counters['unauthorized'] += 1
                return self.send(401, {})
            counters['authenticated_gets'] += 1
            if path == BASE:
                return self.send(200, dict(total_entries=5, dag_runs=[dict(
                    dag_run_id=f'synthetic_{i}', run_after=d.isoformat(),
                    state=['success', 'failed', 'failed', 'failed', 'running'][i]) for i,d in enumerate(dates)]))
            for i,d in enumerate(dates):
                prefix = BASE+f'/synthetic_{i}'
                if path == prefix+'/taskInstances':
                    items = [dict(task_id=t, state=('running' if i==4 else 'failed' if i in (1,2,3) and t=='validate_results' else 'success'),
                        start_date=d.isoformat(), end_date=(d+timedelta(seconds=10)).isoformat()) for t in TASKS]
                    return self.send(200, dict(task_instances=items, total_entries=4))
                if path == prefix+'/taskInstances/execute_reconciliation/xcomEntries/return_value':
                    status = 'FAIL' if i==1 else 'INSUFFICIENT_DATA' if i==3 else 'PASS'
                    checks=[] if i==3 else [dict(rule=r, status='FAIL' if i==1 and j==0 else 'PASS', violations=1 if i==1 and j==0 else 0) for j,r in enumerate(RULES)]
                    return self.send(200, dict(value=dict(started_at=(d+timedelta(seconds=1)).isoformat(),
                        completed_at=(d+timedelta(seconds=9)).isoformat(), status=status,
                        reason='source_unavailable_or_incompatible' if i==3 else 'snapshot_checked', checks=checks)))
            self.send(404, {})
    server = ThreadingHTTPServer(('127.0.0.1',18064), Airflow)
    thread=threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings=Settings(environment='test', llm_provider='disabled', llm_url=None,
        llm_api_key=None, approval_db_path=None, remediation_enabled=False,
        airflow_enabled=True, airflow_url='http://127.0.0.1:18064', airflow_api_token=token)
    app=create_app(settings)
    app.app.state.prometheus_collector=Metrics()
    try:
        uvicorn.run(app, host='127.0.0.1', port=18063, access_log=False, log_config=None)
    finally:
        server.shutdown()

if __name__ == '__main__':
    main()
