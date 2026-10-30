"""Java 21 logging/security regressions on a fresh tmpfs PostgreSQL container."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'local/results/step75'
OUT.mkdir(parents=True, exist_ok=True)
name, password = 'bankops-step75-tests-' + secrets.token_hex(5), secrets.token_urlsafe(32)


def docker(args):
    result = subprocess.run(['docker', *args], text=True, capture_output=True)
    assert result.returncode == 0, 'Disposable backend database operation failed'
    return result.stdout


try:
    docker(['run', '-d', '--rm', '--name', name, '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,nodev',
            '-e', 'POSTGRES_USER=bankops_test', '-e', 'POSTGRES_DB=bankops_test',
            '-e', 'POSTGRES_PASSWORD=' + password, '-p', '127.0.0.1::5432', 'postgres:17'])
    for _ in range(60):
        result = subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'bankops_test'], capture_output=True)
        if result.returncode == 0:
            break
        time.sleep(1)
    ports = json.loads(docker(['inspect', name, '--format', '{{json .NetworkSettings.Ports}}']))
    port = ports['5432/tcp'][0]['HostPort']
    env = {k: v for k, v in os.environ.items() if not k.startswith(('BANKOPS_', 'SPRING_', 'OTEL_'))}
    env.update(JAVA_HOME='C:/Program Files/Eclipse Adoptium/jdk-21.0.12.101-hotspot',
        BANKOPS_TEST_DB_URL=f'jdbc:postgresql://127.0.0.1:{port}/bankops_test',
        BANKOPS_TEST_DB_USER='bankops_test', BANKOPS_TEST_DB_PASSWORD=password)
    classes = ['StructuredLoggingIntegrationTests', 'LoggingFailureIntegrationTests', 'ApiSecurityFilterTests']
    result = subprocess.run([str(ROOT / 'backend/banking-service/mvnw.cmd'), '--offline', '--batch-mode',
        '--no-transfer-progress', '-Dtest=' + ','.join(classes), 'test'], cwd=ROOT / 'backend/banking-service',
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    (OUT / 'backend-regressions.log').write_text(result.stdout.replace(password, '[REDACTED]'), encoding='utf-8')
    print(result.stdout[-1800:].replace(password, '[REDACTED]'))
    assert result.returncode == 0, 'Backend tests failed; inspect private log'
    suites = [ET.parse(ROOT / 'backend/banking-service/target/surefire-reports' /
        ('TEST-com.bankops.banking.' + cls + '.xml')).getroot().attrib for cls in classes]
    summary = {key: sum(int(s.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    (OUT / 'backend-results.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
finally:
    subprocess.run(['docker', 'stop', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
