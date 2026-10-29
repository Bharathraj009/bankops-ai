"""Image CI must retain full image coverage and a non-publishing security gate."""
from pathlib import Path
import re
import runpy

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_summary_handles_null_findings_without_printing_metadata():
    summarize = runpy.run_path(str(ROOT / '.github/scripts/image_summary.py'))['summary']
    assert summarize({'Metadata': {'Env': ['SECRET=private']}, 'Results': [
        {'Vulnerabilities': None}, {'Vulnerabilities': [
            {'Severity': 'HIGH'}, {'Severity': 'CRITICAL'}, {'Severity': 'HIGH'}]}]}) == (2, 1)


def workflow():
    return yaml.load((ROOT / '.github/workflows/images.yml').read_text(), Loader=yaml.BaseLoader)


def test_every_maintained_dockerfile_is_built_with_its_context():
    items = workflow()['jobs']['images']['strategy']['matrix']['include']
    expected = {'backend/banking-service/Dockerfile': 'backend/banking-service',
                'agent/Dockerfile': 'agent', 'frontend/Dockerfile': 'frontend',
                'airflow/Dockerfile': 'airflow', 'airflow/Dockerfile.test': 'airflow',
                'local/Dockerfile.database': '.', 'local/Dockerfile.jaeger': 'local'}
    assert {item['dockerfile']: item['context'] for item in items} == expected
    assert len({item['image'] for item in items}) == len(expected)
    for dockerfile, context in expected.items():
        assert (ROOT / context / '.dockerignore').is_file()
        for line in (ROOT / dockerfile).read_text().splitlines():
            if line.startswith('FROM '):
                assert re.fullmatch(r'FROM \S+@sha256:[0-9a-f]{64}( AS \w+)?', line)


def test_workflow_permissions_triggers_and_non_publishing_build():
    value = workflow()
    assert set(value['on']) == {'push', 'pull_request', 'workflow_dispatch'}
    assert value['permissions'] == {'contents': 'read'}
    job = value['jobs']['images']
    assert job['strategy']['fail-fast'] == 'false'
    assert job['strategy']['max-parallel'] == '2'
    steps = job['steps']
    build = next(step for step in steps if step.get('id') == 'build')['with']
    assert build['push'] == 'false'
    assert build['platforms'] == 'linux/amd64'
    assert build['outputs'].startswith('type=docker,dest=')
    assert not {'build-args', 'secrets', 'secret-envs', 'ssh'} & build.keys()
    assert re.search(r'@sha256:[0-9a-f]{64}$', value['env']['TRIVY_IMAGE'])


def test_security_gate_cannot_silently_pass_or_publish_secret_artifacts():
    text = (ROOT / '.github/workflows/images.yml').read_text()
    assert '--ignore-unfixed=false' in text
    assert '--severity HIGH,CRITICAL' in text
    assert '--ignorefile /dev/null' in text
    assert '--exit-code 1 /reports/scan.json' in text
    assert '--format cyclonedx' in text
    assert '/var/run/docker.sock' not in text
    assert 'continue-on-error' not in text
    assert 'secrets.' not in text
    upload = next(step for step in workflow()['jobs']['images']['steps']
                  if step.get('uses', '').startswith('actions/upload-artifact@'))
    assert upload['if'].startswith('always()')
    assert 'bankops-image.tar' not in upload['with']['path']
