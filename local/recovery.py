"""Step 68: fresh generated project only; never interrupts retained local/dev services."""
import base64
from datetime import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import runpy
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
RUNTIME = {'postgres', 'banking', 'agent', 'frontend', 'airflow-metadata', 'airflow', 'prometheus', 'grafana', 'jaeger'}
MARKERS = [('postgres', '/var/lib/postgresql/data'), ('airflow-metadata', '/var/lib/postgresql/data'),
           ('airflow', '/opt/airflow/logs'), ('airflow', '/opt/airflow/local-auth'),
           ('agent', '/home/agent/state'), ('prometheus', '/prometheus'), ('grafana', '/var/lib/grafana')]
PORTS = {'frontend': 15268, 'airflow': 18068, 'prometheus': 19068, 'grafana': 13068, 'jaeger': 16668}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def isolated_subnets(existing, count):
    used = [ipaddress.ip_network(value) for value in existing if ':' not in value]
    chosen = []
    for index in range(256):
        candidate = ipaddress.ip_network(f'10.68.{index}.0/24')
        if not any(candidate.overlaps(network) for network in used):
            chosen.append(str(candidate))
            if len(chosen) == count:
                return chosen
    raise ValueError('No unused recovery subnet available; existing networks were preserved')


def docker_subnets(networks):
    return [entry['Subnet'] for network in networks
            for entry in ((network.get('IPAM') or {}).get('Config') or []) if entry.get('Subnet')]


def validate_fixture(config, project, prefix='bankops-step68-'):
    if prefix not in ('bankops-step68-', 'bankops-step69-') or not re.fullmatch(re.escape(prefix) + r'[0-9a-f]{12}', project) or config.get('name') != project:
        raise ValueError('Only a freshly generated Step 68 project is allowed')
    for kind in ('volumes', 'networks'):
        for item in config[kind].values():
            if item.get('external') or not item['name'].startswith(project + '_'):
                raise ValueError('External or retained infrastructure is forbidden')
    if set(config['services']) != RUNTIME | {'prepare', 'migrate', 'grant'}:
        raise ValueError('Unexpected fixture services')
    for service in config['services'].values():
        if any(p.get('host_ip') != '127.0.0.1' for p in service.get('ports', [])):
            raise ValueError('Only loopback interfaces are allowed')
        for mount in service.get('volumes', []):
            if mount['type'] == 'bind' and not mount.get('read_only'):
                raise ValueError('Writable host mounts are forbidden')
    for name in ('banking', 'agent', 'airflow', 'frontend'):
        if any('ADMIN_PASSWORD' in key or 'MIGRATION_DB' in key for key in config['services'][name]['environment']):
            raise ValueError('Application received infrastructure credentials')
    agent = config['services']['agent']
    if 'financial' in agent['networks'] or any('DB_PASSWORD' in k or 'RECONCILIATION_PASSWORD' in k for k in agent['environment']):
        raise ValueError('Agent financial access is forbidden')
    assert agent['environment']['BANKOPS_AGENT_LLM_PROVIDER'] == 'disabled'
    assert agent['environment']['BANKOPS_AGENT_REMEDIATION_ENABLED'] == 'false'
    assert config['services']['banking']['environment']['BANKOPS_CUSTOMER_ENABLED'] == 'false'


def wait_for(check, timeout=180):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (AssertionError, OSError, urllib.error.URLError, ValueError) as error:
            last = type(error).__name__
        time.sleep(2)
    raise AssertionError(f'Recovery deadline exceeded ({last or "condition false"})')


class Recovery:
    def __init__(self):
        self.directory = ROOT / 'results' / ('step68-' + secrets.token_hex(6))
        self.directory.mkdir(parents=True, mode=0o700)
        self.values = runpy.run_path(str(ROOT / 'init.py'))['generate'](self.directory, 'bankops-step68-')
        self.project = self.values['BANKOPS_LOCAL_PROJECT']
        for resource in ('container', 'volume', 'network'):
            existing = self.command(['docker', resource, 'ls', *(['-a'] if resource == 'container' else []), '-q', '--filter',
                                     'label=com.docker.compose.project=' + self.project])
            if existing.strip():
                raise ValueError('Generated project already has resources; refusing to reuse it')
        self.browser = None
        self.startup = None
        self.report = {'project': self.project, 'checks': {}, 'started_at': datetime.now().astimezone().isoformat()}
        self.baseline_hashes = self.migration_hashes()
        self.source = ['docker', 'compose', '--env-file', str(ROOT / '.env.local'), '-f', str(ROOT / 'compose.yaml')]
        source = json.loads(self.command(self.source + ['config', '--format', 'json']))
        source_project = source['name']
        config = json.loads(self.command(['docker', 'compose', '--env-file', str(self.directory / '.env.local'),
                                         '-f', str(ROOT / 'compose.yaml'), 'config', '--format', 'json']))
        for name, service in config['services'].items():
            if 'build' in service:
                del service['build']
                pinned = self.project + '-' + name + ':fixture'
                self.command(['docker', 'image', 'tag', source_project + '-' + name, pinned])
                service['image'] = pinned
                service['pull_policy'] = 'never'
            for port in service.get('ports', []):
                port['published'] = str(PORTS[name])
        network_ids = self.command(['docker', 'network', 'ls', '-q']).split()
        networks = json.loads(self.command(['docker', 'network', 'inspect', *network_ids]))
        used = docker_subnets(networks)
        subnets = isolated_subnets(used, len(config['networks']))
        for network, subnet in zip(config['networks'].values(), subnets):
            network['ipam'] = {'config': [{'subnet': subnet}]}
        # New secret bind belongs exclusively to this generated run.
        for mount in config['services']['prometheus']['volumes']:
            if mount.get('target') == '/run/secrets/banking-token':
                mount['source'] = str(self.directory / '.secrets/banking-token')
        self.reserve = str(uuid.uuid4())
        config['services']['banking']['environment'].update({
            'SPRING_PROFILES_ACTIVE': 'dev,db-secure',
            'BANKOPS_DEV_FUNDING_ACCOUNT_ID': self.reserve,
            'BANKOPS_DEV_RESERVE_BOOTSTRAP_ENABLED': 'true',
            'BANKOPS_DEV_RESERVE_INITIAL_BALANCE': '10000.00',
            'SPRING_DATASOURCE_HIKARI_CONNECTION_TIMEOUT': '2000',
            'SPRING_DATASOURCE_HIKARI_VALIDATION_TIMEOUT': '1000',
        })
        # A deliberate startup barrier proves dependents cannot bypass DB health.
        config['services']['postgres']['healthcheck']['test'] = ['CMD-SHELL', 'test -f /tmp/step68-ready && pg_isready -U bankops -d bankops']
        validate_fixture(config, self.project)
        self.config = config
        path = self.directory / 'compose.json'
        path.write_text(json.dumps(config))
        path.chmod(0o600)
        self.compose = ['docker', 'compose', '-p', self.project, '-f', str(path)]

    def command(self, args, code=None, log=None, timeout=900, allowed=(0,)):
        result = subprocess.run(args, input=code, text=True, capture_output=True, cwd=REPO, timeout=timeout)
        if log:
            output = result.stdout + result.stderr
            for key, value in self.values.items():
                if key != 'BANKOPS_LOCAL_PROJECT':
                    output = output.replace(value, '[REDACTED]')
            (self.directory / log).write_text(output, encoding='utf-8')
        if result.returncode not in allowed:
            raise AssertionError(f'Local command failed (exit {result.returncode}); inspect redacted run logs')
        return result.stdout

    def dc(self, *args, **kwargs):
        return self.command(self.compose + list(args), **kwargs)

    def exec(self, service, code):
        return self.dc('exec', '-T', service, 'python', '-', code=code)

    def mark(self, name, details=True):
        self.report['checks'][name] = details
        self.save()
        print(f'{name}: PASS', flush=True)

    def save(self):
        (self.directory / 'report.json').write_text(json.dumps(self.report, indent=2) + '\n')

    @staticmethod
    def migration_hashes():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (REPO / 'backend/banking-service/src/main/resources/db/migration').glob('V[1-6]__*.sql')}

    def states(self):
        output = self.dc('ps', '-a', '--format', 'json')
        return {item['Service']: item for line in output.splitlines() if line.strip() for item in [json.loads(line)]}

    def healthy(self, *services):
        states = self.states()
        return all(states.get(s, {}).get('Health') == 'healthy' and states[s]['State'] == 'running' for s in services)

    def api(self, path, method='GET', data=None, expected=(200,), headers=None, port=15268, operator=True):
        headers = dict(headers or {})
        if operator:
            headers['Authorization'] = 'Bearer ' + self.values['BANKOPS_BANKING_API_TOKEN']
        if data is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(f'http://127.0.0.1:{port}' + path, method=method,
            data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            with OPENER.open(request, timeout=20) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        assert status in expected, f'HTTP {path}: unexpected status {status}'
        try:
            value = json.loads(raw)
        except ValueError:
            value = None
        return status, value

    def browser_command(self, command, **values):
        self.browser.stdin.write(json.dumps({'command': command, **values}) + '\n')
        self.browser.stdin.flush()
        answer = self.browser.stdout.readline()
        assert answer and json.loads(answer)['ok'], f'Chromium {command} failed'

    def snapshot(self):
        return json.loads(self.exec('airflow', '''
import hashlib,json,os
import psycopg
from reconciliation import reconcile
dsn=psycopg.conninfo.make_conninfo(host='postgres',dbname='bankops',user='bankops_reconciliation',password=os.environ['BANKOPS_RECONCILIATION_PASSWORD'])
with psycopg.connect(dsn) as c:
 c.execute('SET TRANSACTION READ ONLY')
 rows=[c.execute('SELECT * FROM '+t+' ORDER BY id').fetchall() for t in ('accounts','transfers','ledger_entries')]
 history=c.execute('SELECT version,checksum,success FROM flyway_schema_history ORDER BY installed_rank').fetchall()
 c.rollback()
r=reconcile(dsn)
assert r.status=='PASS'
print(json.dumps({'digest':hashlib.sha256(repr(rows).encode()).hexdigest(),'counts':[len(x) for x in rows],'history_digest':hashlib.sha256(repr(history).encode()).hexdigest(),'reconciliation':r.status}))
'''))

    def browser_start(self):
        self.browser_log = (self.directory / 'chromium.log').open('w')
        self.browser = subprocess.Popen(['node', str(ROOT / 'browser-recovery.mjs')], cwd=REPO,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.browser_log, text=True)
        self.browser_command('init', base='http://127.0.0.1:15268', account=self.account, token=self.values['BANKOPS_BANKING_API_TOKEN'])

    def evidence(self):
        return self.api('/monitoring-api/incidents/detect', operator=False)[1]

    def banking_metric(self, value):
        evidence = self.evidence()
        return any(m['name'] == 'banking_availability' and m['status'] == 'ok' and m['value'] == value for m in evidence['evidence']['metrics'])

    def replay_completed_transfer(self):
        # Explicit test replays of an already committed request: never a new key/body.
        status, result = self.api('/api/v1/transfers', 'POST', self.transfer_body,
                                  (200, 500, 503), {'Idempotency-Key': self.key})
        self.replay_statuses.append(status)
        if status != 200:
            return False
        assert result['id'] == self.transfer['id']
        return True

    def dag(self, label):
        code = "import runpy,os; from datetime import datetime,UTC; runpy.run_path('/opt/bankops/start.py')['configure'](); os.execvp('airflow',['airflow','dags','test','bankops_daily_reconciliation',datetime.now(UTC).isoformat()])"
        self.dc('exec', '-T', 'airflow', 'python', '-c', code, log=f'dag-{label}.log')
        text = (self.directory / f'dag-{label}.log').read_text(encoding='utf-8')
        assert 'state=success' in text and 'Reconciliation summary' in text

    def run(self):
        self.dc('config', '--quiet')
        self.startup = subprocess.Popen(self.compose + ['up', '-d', '--wait', '--wait-timeout', '600'],
            cwd=REPO, stdout=(self.directory / 'startup.log').open('w'), stderr=subprocess.STDOUT)
        def postgres_running():
            if self.startup.poll() not in (None, 0):
                raise RuntimeError('Fixture startup failed; inspect startup.log')
            return self.states().get('postgres', {}).get('State') == 'running'
        wait_for(postgres_running)
        time.sleep(8)
        states = self.states()
        assert not any(states.get(s, {}).get('State') == 'running' for s in ('prepare', 'migrate', 'grant', 'banking', 'frontend'))
        self.mark('startup_health_barrier')
        self.dc('exec', '-T', 'postgres', 'touch', '/tmp/step68-ready')
        assert self.startup.wait(timeout=650) == 0
        assert self.healthy(*RUNTIME)
        self.mark('nine_runtime_containers_healthy')
        # Inspect only bounded status/timing metadata, never raw environment output.
        ids = [state['ID'] for state in self.states().values()]
        inspected = json.loads(self.command(['docker', 'inspect', *ids]))
        info = {i['Config']['Labels']['com.docker.compose.service']: i for i in inspected}
        for after, before in [('migrate', 'prepare'), ('grant', 'migrate'), ('banking', 'grant')]:
            assert info[before]['State']['ExitCode'] == 0
            assert info[after]['State']['StartedAt'] >= info[before]['State']['FinishedAt']
        self.mark('startup_migration_order')
        self.mounts = {n: sorted(m['Name'] for m in i['Mounts'] if m['Type'] == 'volume') for n, i in info.items()}
        for service, directory in MARKERS:
            self.dc('exec', '-T', service, 'sh', '-c', f'printf step68-persistent > {directory}/.step68-marker')
        self.api('/api/v1/operator/me', expected=(401,), operator=False)
        self.api('/customer-api/me', expected=(503,), operator=False)
        self.account = self.api('/api/v1/accounts', 'POST', {'accountNumber': 'STEP68-SOURCE', 'currency': 'USD'}, (201,))[1]['id']
        self.destination = self.api('/api/v1/accounts', 'POST', {'accountNumber': 'STEP68-DESTINATION', 'currency': 'USD'}, (201,))[1]['id']
        # Funding is accessible only inside the disposable dev-profile fixture.
        payload = {'url': f'http://banking:8080/api/v1/dev/accounts/{self.account}/fund',
                   'token': self.values['BANKOPS_BANKING_API_TOKEN']}
        code = "let v=''; for await(const c of process.stdin)v+=c; const p=JSON.parse(v); const r=await fetch(p.url,{method:'POST',headers:{Authorization:'Bearer '+p.token,'Content-Type':'application/json','Idempotency-Key':'step68-fund'},body:JSON.stringify({amount:1000})}); if(r.status!==201)process.exit(1);"
        self.dc('exec', '-T', 'frontend', 'node', '--input-type=module', '-e', code, code=json.dumps(payload))
        self.key = 'step68-transfer-' + secrets.token_hex(8)
        self.transfer_body = {'sourceAccountId': self.account, 'destinationAccountId': self.destination, 'amount': 250}
        self.transfer = self.api('/api/v1/transfers', 'POST', self.transfer_body, (201,), {'Idempotency-Key': self.key})[1]
        self.baseline = self.snapshot()
        assert self.baseline['counts'] == [3, 2, 4]
        self.browser_start()
        self.mark('chromium_live_loading_and_initial_state')
        self.dag('before')
        # Stop only the fixture DB; keep the banking process alive to prove reconnect.
        banking_started = info['banking']['State']['StartedAt']
        self.dc('stop', '-t', '20', 'postgres')
        self.browser_command('banking_down')
        self.api('/api/v1/transfers', 'POST', self.transfer_body, (500, 503), {'Idempotency-Key': self.key})
        self.dc('start', 'postgres')
        wait_for(lambda: self.healthy('postgres', 'banking'))
        wait_for(lambda: self.api('/api/v1/accounts/' + self.account)[1]['id'] == self.account, 90)
        self.browser_command('banking_up')
        current = json.loads(self.command(['docker', 'inspect', self.states()['banking']['ID']]))[0]
        assert current['State']['StartedAt'] == banking_started
        self.replay_statuses = []
        replay_started = time.monotonic()
        wait_for(self.replay_completed_transfer, 90)
        assert self.snapshot() == self.baseline
        self.mark('postgres_reconnect_no_backend_restart_no_duplicate_transfer',
                  {'same_key_statuses': self.replay_statuses, 'replay_recovery_seconds': round(time.monotonic()-replay_started, 2)})
        self.dc('stop', '-t', '20', 'banking')
        wait_for(lambda: self.banking_metric(0), 90)
        assert self.api('/monitoring-api/health', operator=False)[0] == 200
        self.browser_command('banking_down')
        self.browser_command('monitoring_down')
        self.dc('start', 'banking')
        wait_for(lambda: self.healthy('banking'))
        wait_for(lambda: self.banking_metric(1), 90)
        self.browser_command('banking_up')
        self.browser_command('monitoring_up')
        assert self.snapshot() == self.baseline
        self.mark('banking_interruption_agent_and_chromium_recovery')
        self.dc('stop', '-t', '20', 'prometheus')
        unavailable = self.evidence()
        assert unavailable['state'] == 'insufficient_data' and unavailable['evidence']['status'] == 'unavailable'
        self.browser_command('monitoring_down')
        self.dc('start', 'prometheus')
        wait_for(lambda: self.healthy('prometheus'))
        wait_for(lambda: self.banking_metric(1), 90)
        self.browser_command('monitoring_up')
        self.mark('prometheus_interruption_fail_closed_and_recovery')
        self.dc('stop', '-t', '20', 'agent')
        self.browser_command('monitoring_down')
        self.dc('start', 'agent')
        wait_for(lambda: self.healthy('agent'))
        self.browser_command('monitoring_up')
        self.mark('agent_restart_chromium_recovery')
        self.dc('restart', '-t', '20', 'grafana')
        wait_for(lambda: self.healthy('grafana'))
        auth = base64.b64encode(('admin:' + self.values['BANKOPS_GRAFANA_ADMIN_PASSWORD']).encode()).decode()
        assert self.api('/api/datasources/uid/bankops-prometheus/health', headers={'Authorization': 'Basic ' + auth}, port=13068, operator=False)[1]['status'] == 'OK'
        self.mark('grafana_restart_datasource_recovery')
        self.dc('restart', '-t', '20', 'jaeger')
        wait_for(lambda: self.healthy('jaeger'))
        # New authenticated reads produce traces after Jaeger's ephemeral store reset.
        self.api('/api/v1/accounts/' + self.account)
        trace_code = "import asyncio,json; from bankops_agent.config import Settings; from bankops_agent.evidence.jaeger import JaegerCollector; r=asyncio.run(JaegerCollector(Settings()).collect()); print(json.dumps({'status':r.status,'count':len(r.traces)}))"
        wait_for(lambda: json.loads(self.dc('exec', '-T', 'agent', 'python', '-c', trace_code))['count'] > 0, 90)
        self.mark('jaeger_receives_new_traces_after_restart')
        self.dc('restart', '-t', '30', 'airflow')
        wait_for(lambda: self.healthy('airflow'), 360)
        self.dag('after')
        assert self.snapshot() == self.baseline
        self.mark('airflow_scheduler_and_real_dag_recovery')
        self.browser_command('close')
        self.browser.stdin.close()
        self.browser.wait(timeout=20)
        self.browser = None
        self.dc('stop', '-t', '30', log='graceful-stop.log')
        states = self.states()
        assert all(states[s]['State'] == 'exited' for s in RUNTIME)
        assert all(states[s]['ExitCode'] != 137 for s in RUNTIME)
        assert states['frontend']['ExitCode'] == 0, 'Frontend must stop cleanly; do not mask real failures'
        self.mark('graceful_shutdown_no_forced_kill', {'exit_codes': {s: states[s]['ExitCode'] for s in sorted(RUNTIME)}})
        self.dc('up', '-d', '--wait', '--wait-timeout', '600', log='restart.log')
        assert self.healthy(*RUNTIME)
        assert self.snapshot() == self.baseline
        ids = [state['ID'] for state in self.states().values()]
        final = json.loads(self.command(['docker', 'inspect', *ids]))
        mounts = {i['Config']['Labels']['com.docker.compose.service']: sorted(m['Name'] for m in i['Mounts'] if m['Type']=='volume') for i in final}
        assert mounts == self.mounts
        for service, directory in MARKERS:
            assert self.dc('exec', '-T', service, 'cat', directory + '/.step68-marker') == 'step68-persistent'
        assert self.api('/api/v1/transfers', 'POST', self.transfer_body, (200,), {'Idempotency-Key': self.key})[1]['id'] == self.transfer['id']
        assert self.snapshot() == self.baseline
        self.api('/api/v1/operator/me', expected=(401,), operator=False)
        self.api('/customer-api/me', expected=(503,), operator=False)
        assert self.migration_hashes() == self.baseline_hashes
        self.mark('full_restart_persistent_volumes_financial_idempotency_and_security')
        self.report['financial_snapshot'] = self.baseline
        self.report['migration_hashes'] = self.baseline_hashes
        self.report['status'] = 'PASS'
        self.save()

    def close(self):
        if self.startup and self.startup.poll() is None:
            self.startup.terminate()
            self.startup.wait(timeout=20)
        if self.browser:
            self.browser.terminate()
            self.browser.wait(timeout=15)
        if hasattr(self, 'browser_log'):
            self.browser_log.close()
        if hasattr(self, 'compose'):
            self.dc('stop', '-t', '30', log='final-stop.log')
        self.report['fixture_stopped_volumes_preserved'] = True
        self.save()


def main():
    run = Recovery()
    try:
        run.run()
    except BaseException as error:
        run.report['status'] = 'FAILED'
        run.report['failure_type'] = type(error).__name__
        run.save()
        raise
    finally:
        run.close()
    print('Recovery verification passed; disposable fixture stopped, volumes preserved', flush=True)
    print(run.directory.relative_to(REPO), flush=True)


if __name__ == '__main__':
    main()
