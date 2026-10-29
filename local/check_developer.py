"""Exercise the operator CLI using fresh Step 69 state; preserve all test volumes."""
import hashlib
import json
from pathlib import Path
import runpy
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
MODULE = runpy.run_path(str(ROOT / 'platform.py'))


def command(args, expected=0):
    result = subprocess.run(args, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert result.returncode == expected, f'Command returned {result.returncode}; expected {expected}'
    return result.stdout


def network_inventory():
    ids = command(['docker', 'network', 'ls', '-q']).split()
    values = json.loads(command(['docker', 'network', 'inspect', *ids]))
    return {v['Name']: {k: v[k] for k in ('Id', 'Internal', 'IPAM', 'Options')} for v in values}


def main():
    identity = secrets.token_hex(6)
    state = ROOT / 'results' / ('step69-' + identity)
    assert not state.exists()
    before_networks = network_inventory()
    cli = [sys.executable, str(ROOT / 'platform.py'), '--fixture', identity]
    report = {'fixture_id': identity, 'status': 'FAILED'}
    started = False
    try:
        started = True
        up = command(cli + ['up'])
        assert 'no rebuild requested' in up
        config = json.loads((state / 'compose.json').read_text())
        dc = ['docker', 'compose', '-f', str(state / 'compose.json')]
        values = dict(line.split('=', 1) for line in (state / '.env.local').read_text().splitlines())
        def safe_log(name, text):
            (state / name).write_text(MODULE['redact'](text, values), encoding='utf-8')
        safe_log('cli-up.log', up)
        command(cli + ['health'])
        command(cli + ['logs', 'frontend'])
        command(cli + ['verify'])
        def snapshot():
            code = "import os,json,hashlib,psycopg; from psycopg.conninfo import make_conninfo; c=psycopg.connect(make_conninfo(host='postgres',dbname='bankops',user='bankops_reconciliation',password=os.environ['BANKOPS_RECONCILIATION_PASSWORD'])); c.execute('SET TRANSACTION READ ONLY'); rows=[c.execute('SELECT * FROM '+t+' ORDER BY id').fetchall() for t in ('accounts','transfers','ledger_entries')]; h=c.execute('SELECT version,checksum,success FROM flyway_schema_history ORDER BY installed_rank').fetchall(); print(json.dumps({'digest':hashlib.sha256(repr(rows).encode()).hexdigest(),'counts':[len(x) for x in rows],'history':hashlib.sha256(repr(h).encode()).hexdigest()})); c.rollback(); c.close()"
            return json.loads(command(dc + ['exec', '-T', 'airflow', 'python', '-c', code]))
        def inspect():
            ids = command(dc + ['ps', '-a', '-q']).split()
            return {v['Config']['Labels']['com.docker.compose.service']: v for v in json.loads(command(['docker', 'inspect', *ids]))}
        initial = snapshot()
        initial_info = inspect()
        initial_mounts = {n: sorted(m['Name'] for m in v['Mounts'] if m['Type']=='volume') for n, v in initial_info.items()}
        warm = command(cli + ['up'])
        assert 'no rebuild requested' in warm
        assert all(inspect()[name]['Id'] == initial_info[name]['Id'] for name in MODULE['RUNTIME'])
        safe_log('cli-warm-up.log', warm)
        command(cli + ['stop'])
        stopped = inspect()
        assert stopped['frontend']['State']['ExitCode'] == 0
        assert all(stopped[name]['State']['Status'] == 'exited' and stopped[name]['State']['ExitCode'] != 137 for name in MODULE['RUNTIME'])
        command(cli + ['health'], expected=1)
        safe_log('cli-resume.log', command(cli + ['up']))
        command(cli + ['verify'])
        command(cli + ['restart', 'frontend', 'agent'])
        command(cli + ['verify'])
        final = inspect()
        final_mounts = {n: sorted(m['Name'] for m in v['Mounts'] if m['Type']=='volume') for n, v in final.items()}
        assert initial_mounts == final_mounts and snapshot() == initial
        # Invalid server credential configuration must remain a real startup failure.
        bad = subprocess.run(['docker', 'run', '--name', 'bankops-step69-invalid-' + identity,
            '--network', 'none', '-e', 'BANKOPS_AGENT_API_TOKEN=short', config['services']['frontend']['image']],
            capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=REPO, timeout=60)
        assert bad.returncode == 1 and 'Invalid server API credential configuration' in bad.stderr + bad.stdout
        safe_log('frontend-negative.log', bad.stdout + bad.stderr)
        after_networks = network_inventory()
        assert all(after_networks[name] == value for name, value in before_networks.items())
        report.update(status='PASS', clean_frontend_exit=0, genuine_frontend_failure_exit=1,
                      financial_snapshot=initial, existing_networks_unchanged=True,
                      cached_images_reused=True, runtime_ids_preserved_on_warm_up=True,
                      all_service_routes_verified=True, stopped_start_restart_verified=True)
    finally:
        if started and (state / 'compose.json').exists():
            command(cli + ['stop'])
            report['fixture_stopped_volumes_preserved'] = True
        if state.exists():
            (state / 'developer-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print(state.relative_to(REPO))


if __name__ == '__main__':
    main()
