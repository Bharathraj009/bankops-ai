"""Opt-in local verification using the real, unchanged agent and Airflow API.

Viewer credentials are read server-side from ignored local configuration and held
only in memory. No DAG mutation, banking connection or synthetic collector exists
in this launcher. Run --inspect for safe aggregate diagnostics, --serve to start.
"""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'agent' / 'src'))
BASE = 'http://127.0.0.1:18081'


def get_token():
    values = dict(line.split('=', 1) for line in (ROOT / 'airflow' / '.env.local').read_text().splitlines()
                  if '=' in line and not line.startswith('#'))
    request = urllib.request.Request(BASE + '/auth/token', method='POST',
        data=json.dumps({'username': 'agentviewer', 'password': values['BANKOPS_AIRFLOW_VIEWER_PASSWORD']}).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=10) as response:
        return json.load(response)['access_token']


def get(path, token=None):
    headers = {} if token is None else {'Authorization': 'Bearer ' + token}
    request = urllib.request.Request(BASE + path, headers=headers)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=10) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--inspect', action='store_true')
    mode.add_argument('--serve', action='store_true')
    parser.add_argument('--unavailable-source', action='store_true',
        help='Serve with a fixed closed loopback source to verify safe unavailability; no real service is stopped.')
    args = parser.parse_args()
    try:
        token = get_token()
        if args.inspect:
            health = get('/api/v2/monitor/health')
            dag = get('/api/v2/dags/bankops_daily_reconciliation', token)
            listing = get('/api/v2/dags/bankops_daily_reconciliation/dagRuns?limit=10&order_by=-run_after', token)
            print(json.dumps({'health': {k: v.get('status') for k, v in health.items() if isinstance(v, dict)},
                'dag_paused': dag['is_paused'], 'total_runs': listing['total_entries'],
                'runs': [{'observed_at': r['run_after'], 'state': r['state'],
                    'age_days': round((datetime.now(UTC)-datetime.fromisoformat(r['run_after'].replace('Z', '+00:00'))).total_seconds()/86400, 2)}
                    for r in listing['dag_runs']]}))
            return
        # Import normal startup only after credentials have been safely obtained.
        # Explicit kwargs override any ambient opt-ins; no approvals/remediation/LLM.
        import logging.config
        import uvicorn
        from bankops_agent.app import create_app
        from bankops_agent.config import Settings
        from bankops_agent.logging import create_logger
        settings = Settings(environment='dev', host='127.0.0.1', port=18063,
            airflow_enabled=True, airflow_url='http://127.0.0.1:18999' if args.unavailable_source else BASE, airflow_api_token=token,
            airflow_window_seconds=604800, airflow_max_runs=10, airflow_timeout_seconds=15,
            llm_provider='disabled', llm_url=None, llm_api_key=None, approval_db_path=None,
            remediation_enabled=False, prometheus_url='http://127.0.0.1:9090',
            prometheus_timeout_seconds=1)
        logging.config.dictConfig({'version': 1, 'disable_existing_loggers': True,
            'handlers': {'discard': {'class': 'logging.NullHandler'}},
            'root': {'handlers': ['discard'], 'level': 'CRITICAL'}})
        uvicorn.run(create_app(settings, logger=create_logger()), host='127.0.0.1', port=18063,
            log_config=None, access_log=False, server_header=False)
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        raise SystemExit('Local Airflow verification unavailable; check local service health and viewer configuration.') from None


if __name__ == '__main__':
    main()
