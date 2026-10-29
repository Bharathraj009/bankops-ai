"""Read-only verification of the generated Step 67 project; never accepts live targets."""
import base64
import hashlib
import json
import re
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(port, path, expected=200, headers=None):
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', headers=headers or {})
    try:
        with OPENER.open(req, timeout=15) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, data = error.code, error.read()
    assert status == expected, f'{port} {path}: expected {expected}, received {status}'
    return data


def main(state=ROOT, compose=None, ports=None, emit=True):
    values = dict(line.split('=', 1) for line in (state / '.env.local').read_text().splitlines())
    assert re.fullmatch(r'bankops-step(67|69)-[0-9a-f]{12}', values['BANKOPS_LOCAL_PROJECT'])
    compose = compose or ['docker', 'compose', '--env-file', str(state / '.env.local'), '-f', str(ROOT / 'compose.yaml')]
    def check(port, *args, **kwargs):
        return request((ports or {}).get(port, port), *args, **kwargs)
    def run(*args, code=None):
        result = subprocess.run(compose + list(args), input=code, capture_output=True, text=True, cwd=REPO)
        assert result.returncode == 0, 'Compose verification command failed; inspect local service health/logs'
        return result.stdout
    run('config', '--quiet')
    configuration = json.loads(run('config', '--format', 'json'))
    services = configuration['services']
    for name in ('banking', 'agent', 'frontend', 'airflow'):
        env = services[name]['environment']
        assert not any('ADMIN_PASSWORD' in key or 'MIGRATION_DB' in key for key in env)
    assert not any('DB_PASSWORD' in key or 'RECONCILIATION_PASSWORD' in key for key in services['agent']['environment'])
    assert 'financial' not in services['agent']['networks']
    for service in services.values():
        assert all(port['host_ip'] == '127.0.0.1' for port in service.get('ports', []))
    check(15173, '/')
    check(15173, '/api/v1/operator/me', 401)
    check(15173, '/api/v1/operator/me', headers={'Authorization': 'Bearer ' + values['BANKOPS_BANKING_API_TOKEN']})
    check(15173, '/api/v1/dev/fund', 404)
    check(15173, '/customer-api/me', 503)
    check(15173, '/monitoring-api/health')
    check(15173, '/monitoring-api/incidents/detect')
    check(15173, '/monitoring-api/health', 403, {'Origin': 'https://foreign.invalid'})
    targets = json.loads(check(19097, '/api/v1/targets'))['data']['activeTargets']
    assert targets and all(target['health'] == 'up' for target in targets)
    auth = base64.b64encode(('admin:' + values['BANKOPS_GRAFANA_ADMIN_PASSWORD']).encode()).decode()
    grafana = json.loads(check(13007, '/api/datasources/uid/bankops-prometheus/health', headers={'Authorization': 'Basic ' + auth}))
    assert grafana['status'] == 'OK'
    check(16687, '/api/v3/services')
    check(18087, '/api/v2/monitor/health')
    # Execute the actual Airflow reconciliation code with its SELECT-only identity.
    code = '''
import hashlib,json,os
import psycopg
from psycopg.conninfo import make_conninfo
from reconciliation import reconcile
dsn=make_conninfo(host='postgres',dbname='bankops',user='bankops_reconciliation',password=os.environ['BANKOPS_RECONCILIATION_PASSWORD'])
def snapshot():
    with psycopg.connect(dsn) as c:
        rows=[c.execute('SELECT * FROM public.'+t+' ORDER BY id').fetchall() for t in ('accounts','transfers','ledger_entries')]
        c.rollback()
        return hashlib.sha256(repr(rows).encode()).hexdigest()
before=snapshot()
with psycopg.connect(dsn) as c:
    assert c.execute('SHOW transaction_read_only').fetchone()[0]=='on'
    c.rollback()
    c.execute('SET TRANSACTION READ WRITE')
    try:
        c.execute('UPDATE public.accounts SET balance=balance WHERE false')
    except psycopg.errors.InsufficientPrivilege:
        c.rollback()
    else:
        c.rollback()
        raise AssertionError('Reconciliation write ACL is unsafe')
result=reconcile(dsn)
assert result.status=='PASS'
assert before==snapshot()
print(json.dumps({'reconciliation':result.status,'financial_snapshot_unchanged':True,'financial_snapshot_digest':before,'write_denied':True}))
'''
    reconciliation = json.loads(run('exec', '-T', 'airflow', 'python', '-', code=code))
    # A failed/missing Jaeger collector must fail this check as well.
    run('exec', '-T', 'agent', 'python', '-c', "import urllib.request; urllib.request.urlopen('http://jaeger:16686/api/v3/services',timeout=5)")
    trace_evidence = json.loads(run('exec', '-T', 'agent', 'python', '-c',
        "import asyncio,json; from bankops_agent.config import Settings; "
        "from bankops_agent.evidence.jaeger import JaegerCollector; "
        "r=asyncio.run(JaegerCollector(Settings()).collect()); "
        "assert r.status in ('ok','missing'); "
        "print(json.dumps({'status':r.status,'trace_count':len(r.traces)}))"))
    migrations = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((REPO / 'backend/banking-service/src/main/resources/db/migration').glob('V[1-6]__*.sql'))}
    report = {'http_and_proxy_checks': 'PASS', 'prometheus_targets': 'UP', 'grafana_datasource': 'OK',
              'jaeger_connectivity': 'PASS', 'agent_trace_evidence': trace_evidence,
              **reconciliation, 'migration_hashes': migrations}
    (state / 'results').mkdir(exist_ok=True)
    (state / 'results/verification.json').write_text(json.dumps(report, indent=2) + '\n')
    if emit:
        print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    main()
