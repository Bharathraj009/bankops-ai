"""Local runtime configuration and credential-safety regression tests."""
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_postgres_async_metadata_driver_loads_without_connecting(monkeypatch):
    """Airflow 3.3 derives an asyncpg URL even when metadata uses psycopg2."""
    import asyncio
    import asyncpg
    from sqlalchemy.ext.asyncio import create_async_engine

    def forbidden(*args, **kwargs):
        raise AssertionError('Driver initialization must not connect to a database')

    monkeypatch.setattr(asyncpg, 'connect', forbidden)
    engine = create_async_engine('postgresql+asyncpg://synthetic:unused@127.0.0.1:1/unavailable')
    asyncio.run(engine.dispose())


def test_local_compose_isolated_bounded_and_localhost():
    value = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    assert set(value['services']) == {'airflow','airflow-metadata'}
    runtime = value['services']['airflow']
    metadata = value['services']['airflow-metadata']
    assert runtime['ports'] == ['127.0.0.1:18081:8080']
    assert 'ports' not in metadata
    assert runtime['environment']['AIRFLOW__CORE__EXECUTOR'] == 'LocalExecutor'
    assert runtime['environment']['AIRFLOW__CORE__PARALLELISM'] == '1'
    assert runtime['environment']['AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION'] == 'true'
    assert runtime['environment']['AIRFLOW__LOGGING__LOGGING_LEVEL'] == 'INFO'
    assert runtime['mem_limit'] == '2304m' and metadata['mem_limit'] == '384m'
    assert 'metadata:/var/lib/postgresql/data' in metadata['volumes']
    for name in ('BANKOPS_AIRFLOW_UI_PASSWORD','BANKOPS_RECONCILIATION_PASSWORD','BANKOPS_AIRFLOW_METADATA_PASSWORD'):
        assert runtime['environment'][name].startswith('${' + name + ':?')
    assert 'BANKOPS_RECONCILIATION_DSN' not in runtime['environment']
    assert metadata['environment']['POSTGRES_USER']=='airflow_admin'
    assert 'BANKOPS_AIRFLOW_METADATA_ADMIN_PASSWORD' in metadata['environment']['POSTGRES_PASSWORD']
    assert 'BANKOPS_AIRFLOW_METADATA_ADMIN_PASSWORD' not in runtime['environment']
    assert './runtime/metadata-init.sh:/docker-entrypoint-initdb.d/10-metadata-role.sh:ro' in metadata['volumes']
    script=(ROOT/'runtime/metadata-init.sh').read_text()
    assert 'NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS' in script
    assert 'ALTER DATABASE airflow OWNER TO airflow' in script


def test_startup_credentials_not_printed(tmp_path,monkeypatch,capsys):
    module = runpy.run_path(str(ROOT / 'runtime/start.py'))
    configure = module['configure']
    monkeypatch.setitem(configure.__globals__,'Path',lambda _:tmp_path / 'auth' / 'passwords.json')
    monkeypatch.setenv('BANKOPS_AIRFLOW_METADATA_PASSWORD','PRIVATE@password')
    monkeypatch.setenv('BANKOPS_RECONCILIATION_PASSWORD','PRIVATE banking password')
    monkeypatch.setenv('BANKOPS_AIRFLOW_UI_PASSWORD','PRIVATE ui password')
    import os
    with monkeypatch.context() as patch:
        environment = dict(os.environ)
        patch.setattr(os,'environ',environment)
        configure()
        assert 'PRIVATE%40password' in environment['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN']
        assert 'bankops_reconciliation' in environment['BANKOPS_RECONCILIATION_DSN']
        assert 'bankops-ai-postgres-1' in environment['BANKOPS_RECONCILIATION_DSN']
    assert capsys.readouterr() == ('','')


def test_role_provisioning_repeatable_and_no_banking_dml(tmp_path,monkeypatch,capsys):
    module = runpy.run_path(str(ROOT / 'runtime/provision.py'))
    main = module['main']
    monkeypatch.setitem(main.__globals__,'__file__',str(tmp_path / 'runtime/provision.py'))
    for name in ('BANKOPS_AIRFLOW_METADATA_PASSWORD','BANKOPS_AIRFLOW_UI_PASSWORD','BANKOPS_RECONCILIATION_PASSWORD','BANKOPS_AIRFLOW_JWT_SECRET'):
        monkeypatch.delenv(name,raising=False)
    calls = []
    def execute(arguments,**kwargs):
        calls.append((arguments,kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module['subprocess'],'run',execute)
    main()
    first = (tmp_path / '.env.local').read_text()
    main()
    assert (tmp_path / '.env.local').read_text() == first
    for arguments,options in calls:
        assert first.splitlines()[2].split('=',1)[1] not in str(arguments)
        statement = options['input']
        assert 'GRANT SELECT ON' in statement and 'Role is not strictly read only' in statement
        assert not any(word in statement for word in ('UPDATE accounts','DELETE FROM accounts','INSERT INTO accounts','DISABLE TRIGGER'))
    output = capsys.readouterr().out
    assert all(line.split('=',1)[1] not in output for line in first.splitlines())


def test_provision_failure_suppresses_details(tmp_path,monkeypatch,capsys):
    module = runpy.run_path(str(ROOT / 'runtime/provision.py'))
    main = module['main']
    monkeypatch.setitem(main.__globals__,'__file__',str(tmp_path / 'runtime/provision.py'))
    monkeypatch.setattr(module['subprocess'],'run',lambda *args,**kwargs:SimpleNamespace(returncode=1,stderr='PRIVATE'))
    with pytest.raises(SystemExit) as error: main()
    assert 'PRIVATE' not in str(error.value)
    assert not (tmp_path / '.env.local').exists()
    assert capsys.readouterr() == ('','')


def test_local_inspection_disables_proxies(monkeypatch):
    import io
    import urllib.request
    module = runpy.run_path(str(ROOT / 'runtime/inspect_local.py'))
    class Opener:
        def open(self,request,timeout):
            assert request.full_url.startswith('http://127.0.0.1:18081/') and timeout == 10
            return io.BytesIO(b'{"status":"ok"}')
    def build(handler):
        assert isinstance(handler,urllib.request.ProxyHandler) and handler.proxies == {}
        return Opener()
    monkeypatch.setattr(urllib.request,'build_opener',build)
    assert module['api']('/health') == {'status':'ok'}


def test_viewer_principal_separate_from_admin(tmp_path,monkeypatch,capsys):
    import json
    module=runpy.run_path(str(ROOT / 'runtime/start.py'))
    configure=module['configure']
    monkeypatch.setitem(configure.__globals__,'Path',lambda _:tmp_path / 'auth' / 'passwords.json')
    for key,value in {'BANKOPS_AIRFLOW_METADATA_PASSWORD':'PRIVATE metadata','BANKOPS_AIRFLOW_UI_PASSWORD':'PRIVATE admin',
                      'BANKOPS_RECONCILIATION_PASSWORD':'PRIVATE banking','BANKOPS_AIRFLOW_VIEWER_PASSWORD':'PRIVATE viewer'}.items():
        monkeypatch.setenv(key,value)
    import os
    with monkeypatch.context() as patch:
        patch.setattr(os,'environ',dict(os.environ))
        configure()
    passwords=json.loads((tmp_path / 'auth/passwords.json').read_text())
    assert passwords == {'localadmin':'PRIVATE admin','agentviewer':'PRIVATE viewer'}
    configuration=yaml.safe_load((ROOT / 'compose.yaml').read_text())
    assert configuration['services']['airflow']['environment']['AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS'] == 'localadmin:admin,agentviewer:viewer'
    assert capsys.readouterr() == ('','')
