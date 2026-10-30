"""Run Airflow/reconciliation tests on a disposable internal Docker network."""
import json
import ipaddress
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'local/results/step74'
out.mkdir(parents=True, exist_ok=True)
suffix = secrets.token_hex(5)
network, database = 'bankops-step74-net-' + suffix, 'bankops-step74-db-' + suffix
password = secrets.token_urlsafe(32)


def command(args, check=True):
    result = subprocess.run(['docker', *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if check and result.returncode:
        raise RuntimeError('Docker verification operation failed; no credentials printed')
    return result


try:
    identifiers = command(['network', 'ls', '-q']).stdout.split()
    existing = json.loads(command(['network', 'inspect', *identifiers]).stdout)
    occupied = [ipaddress.ip_network(item['Subnet']) for row in existing
                for item in (row.get('IPAM', {}).get('Config') or []) if item.get('Subnet')]
    subnet = next(ipaddress.ip_network(f'10.253.{number}.0/24') for number in range(74, 254)
                  if not any(ipaddress.ip_network(f'10.253.{number}.0/24').overlaps(other)
                             for other in occupied if other.version == 4))
    command(['network', 'create', '--internal', '--subnet', str(subnet), network])
    command(['run', '-d', '--rm', '--name', database, '--network', network,
             '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,nodev',
             '-e', 'POSTGRES_USER=bankops_test', '-e', 'POSTGRES_DB=bankops_test',
             '-e', 'POSTGRES_PASSWORD=' + password, 'postgres:17'])
    for _ in range(90):
        if command(['exec', database, 'pg_isready', '-U', 'bankops_test'], check=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Disposable database not ready')
    result = command(['run', '--rm', '--name', 'bankops-step74-airflow-' + suffix,
        '--network', network, '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONPATH=/workspace/airflow',
        '-e', f'BANKOPS_RECONCILIATION_TEST_DSN=host={database} dbname=bankops_test user=bankops_test password={password}',
        '--mount', f'type=bind,source={ROOT.as_posix()},target=/workspace,readonly',
        '-w', '/workspace/airflow', '--entrypoint', 'python',
        'bankops-step71-remediation/airflow-test:final', '-m', 'pytest', '-q', '-W', 'error', '-p', 'no:cacheprovider'], check=False)
    clean = result.stdout.replace(password, '[REDACTED]')
    (out / 'airflow-regressions.log').write_text(clean, encoding='utf-8')
    print(clean[-4000:])
    assert result.returncode == 0, 'Airflow regressions failed; inspect private log'
finally:
    command(['stop', database], check=False)
    command(['network', 'rm', network], check=False)
