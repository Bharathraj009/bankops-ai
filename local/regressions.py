"""Run database-backed regressions exclusively against a dedicated test cluster."""
import os
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-only', action='store_true', help='Run Airflow/database suites without repeating Maven')
    args = parser.parse_args()
    values = dict(line.split('=', 1) for line in (ROOT / '.env.local').read_text().splitlines())
    project = values['BANKOPS_LOCAL_PROJECT']
    assert project.startswith('bankops-step67-')
    compose = ['docker', 'compose', '--env-file', str(ROOT / '.env.local'), '-f', str(ROOT / 'regression.compose.yaml')]
    subprocess.run(compose + ['up', '-d', '--wait'], check=True)
    env = {key: value for key, value in os.environ.items() if not key.startswith(('BANKOPS_', 'SPRING_', 'OTEL_'))}
    password = values['BANKOPS_POSTGRES_ADMIN_PASSWORD']
    env.update(BANKOPS_TEST_DB_URL='jdbc:postgresql://127.0.0.1:15567/bankops_test',
               BANKOPS_TEST_DB_USER='bankops_test', BANKOPS_TEST_DB_PASSWORD=password,
               BANKOPS_RECONCILIATION_TEST_DSN=f'host=host.docker.internal port=15567 dbname=bankops_test user=bankops_test password={password}')
    env['BANKOPS_DATABASE_SECURITY_TEST_DSN'] = env['BANKOPS_RECONCILIATION_TEST_DSN']
    env['JAVA_HOME'] = os.environ.get('JAVA_HOME', 'C:/Program Files/Java/jdk-25')
    def run(name, command, cwd=REPO):
        with (ROOT / 'results' / name).open('w') as log:
            result = subprocess.run(command, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        assert result.returncode == 0, f'{name}: FAILED; inspect ignored log'
        print(f'{name}: PASS', flush=True)
    try:
        run('airflow-database-tests.log', ['docker', 'run', '--rm', '-e', 'PYTHONDONTWRITEBYTECODE=1',
            '-e', 'PYTHONPATH=/workspace/airflow', '-e', 'BANKOPS_RECONCILIATION_TEST_DSN',
            '-e', 'BANKOPS_DATABASE_SECURITY_TEST_DSN',
            '-v', f'{REPO.as_posix()}:/workspace:ro', '-w', '/workspace', 'bankops-airflow-step63-tests',
            'python', '-m', 'pytest', '-q', '-W', 'error', '-p', 'no:cacheprovider', 'airflow/tests', 'database/tests', 'database/integration'])
        mvn = REPO / 'backend/banking-service/mvnw.cmd' if os.name == 'nt' else REPO / 'backend/banking-service/mvnw'
        if not args.database_only:
            run('banking-tests.log', [str(mvn), '-B', 'test'], REPO / 'backend/banking-service')
    finally:
        subprocess.run(compose + ['stop'], check=True)


if __name__ == '__main__':
    main()
