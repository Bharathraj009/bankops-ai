"""Guard the CI-only database selector without connecting to any database."""
from pathlib import Path
import runpy

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
configure = runpy.run_path(str(ROOT / '.github/scripts/database_env.py'))['configuration']


def environment():
    return dict(GITHUB_ACTIONS='true', CI='true', CI_POSTGRES_PORT='55470',
                GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1')


def test_database_target_cannot_be_overridden():
    env = environment() | {'BANKOPS_TEST_DB_URL': 'jdbc:postgresql://development/bankops',
                           'BANKOPS_DB_ADMIN_DSN': 'host=development'}
    values = configure(env)
    assert values['BANKOPS_TEST_DB_URL'] == 'jdbc:postgresql://127.0.0.1:55470/bankops_test'
    assert 'host=127.0.0.1' in values['BANKOPS_RECONCILIATION_TEST_DSN']
    assert 'development' not in str(values)


@pytest.mark.parametrize('key,value', [('CI', 'false'), ('GITHUB_ACTIONS', 'false'),
    ('CI_POSTGRES_PORT', '5432\nhost=development'), ('CI_POSTGRES_PORT', '0'),
    ('GITHUB_RUN_ID', 'x'), ('GITHUB_RUN_ATTEMPT', '1\nINJECT=value')])
def test_invalid_context_fails_before_export(key, value):
    with pytest.raises(ValueError):
        configure(environment() | {key: value})


def test_workflow_contract_and_existing_paths():
    # BaseLoader preserves GitHub's YAML 1.2 `on` key (PyYAML safe_load is YAML 1.1).
    workflow = yaml.load((ROOT / '.github/workflows/ci.yml').read_text(), Loader=yaml.BaseLoader)
    assert set(workflow['on']) == {'push', 'pull_request', 'workflow_dispatch'}
    assert workflow['permissions'] == {'contents': 'read'}
    assert len(workflow['jobs']) == 4
    for job in workflow['jobs'].values():
        assert job['runs-on'] == 'ubuntu-24.04'
        assert int(job['timeout-minutes']) <= 25
        for step in job['steps']:
            if 'working-directory' in step:
                assert (ROOT / step['working-directory']).is_dir()
            if step.get('uses', '').startswith('actions/checkout@'):
                assert step['with']['persist-credentials'] == 'false'
    for path in ('backend/banking-service/mvnw', 'agent/requirements-test.lock',
                 'airflow/Dockerfile.test', 'frontend/package-lock.json',
                 'frontend/playwright.config.ts', 'database/integration/test_scram.py'):
        assert (ROOT / path).is_file()
