"""No live DB: credential handling, repeatability, rollback and deployment contracts."""
import base64
import hashlib
import hmac
import importlib.util
from pathlib import Path
import secrets
import sys

import pytest
import yaml

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('database_provision', ROOT/'database/provision.py')
provision=importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


class Result:
    def __init__(self,value):self.value=value
    def fetchone(self):return self.value
    def __iter__(self):return iter(self.value)


class Connection:
    def __init__(self,existing=None):self.existing=existing;self.commands=[]
    def execute(self,statement,parameters=None,**kwargs):
        text=statement if isinstance(statement,str) else statement.as_string()
        self.commands.append(text)
        if 'SELECT EXISTS' in text:return Result((False,))
        if 'SELECT rolpassword FROM' in text:return Result((self.existing,))
        return Result(None)


def passwords():return {role:secrets.token_urlsafe(40) for role in provision.PASSWORDS}


def test_scram_uses_random_salts_and_correct_keys():
    password=secrets.token_urlsafe(40)
    first=provision.scram(password);second=provision.scram(password)
    assert first!=second and password not in first
    algorithm,configuration,keys=first.split('$');iterations,salt=configuration.split(':')
    assert algorithm=='SCRAM-SHA-256' and iterations=='4096'
    salted=hashlib.pbkdf2_hmac('sha256',password.encode(),base64.b64decode(salt),4096)
    stored,server=keys.split(':')
    assert base64.b64decode(stored)==hashlib.sha256(hmac.digest(salted,b'Client Key','sha256')).digest()
    assert base64.b64decode(server)==hmac.digest(salted,b'Server Key','sha256')


def test_prepare_never_sends_plaintext_to_sql_or_logs(capsys):
    values=passwords();connection=Connection();provision.prepare(connection,values)
    rendered='\n'.join(connection.commands)
    assert all(password not in rendered for password in values.values())
    assert rendered.count('SCRAM-SHA-256$')==3
    assert capsys.readouterr()==('','')


def test_repeat_prepare_verifies_credentials_without_rotating():
    values=passwords()
    class Existing(Connection):
        def execute(self,statement,parameters=None,**kwargs):
            if isinstance(statement,str) and 'SELECT rolpassword FROM' in statement:
                return Result((provision.scram(values[parameters[0]]),))
            return super().execute(statement,parameters,**kwargs)
    connection=Existing();provision.prepare(connection,values)
    assert not any('PASSWORD ' in command for command in connection.commands)
    assert sum(command.startswith('ALTER ROLE "bankops_') for command in connection.commands)==3


def test_different_existing_password_is_not_rotated():
    connection=Connection(provision.scram(secrets.token_urlsafe(40)))
    with pytest.raises(ValueError,match='rotation'):provision.prepare(connection,passwords())
    assert not any(' LOGIN PASSWORD ' in command for command in connection.commands)


@pytest.mark.parametrize('value',['short','x'*257,'é'*40,'a'*40+'\n'])
def test_invalid_credentials_fail_before_sql(value):
    values=passwords();values['bankops_runtime']=value;connection=Connection()
    with pytest.raises(ValueError):provision.prepare(connection,values)
    assert connection.commands==[]


def test_shared_credentials_fail_before_sql():
    values={role:'a'*40 for role in provision.PASSWORDS};connection=Connection()
    with pytest.raises(ValueError):provision.prepare(connection,values)
    assert not connection.commands


def test_owner_roles_fail_before_acl_changes():
    class Unsafe(Connection):
        def execute(self,*args,**kwargs):return Result((True,))
    with pytest.raises(ValueError,match='ownership'):provision.prepare(Unsafe(),passwords())


def test_cli_default_disabled_and_errors_suppress_details(monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['provision.py','prepare'])
    monkeypatch.delenv('BANKOPS_DB_SECURITY_APPLY',raising=False)
    with pytest.raises(SystemExit,match='opt-in'):provision.main()
    monkeypatch.setenv('BANKOPS_DB_SECURITY_APPLY','local-only');monkeypatch.setenv('BANKOPS_DB_NAME','synthetic')
    monkeypatch.setenv('BANKOPS_DB_ADMIN_DSN','host=localhost password=PRIVATE')
    for env in provision.PASSWORDS.values():monkeypatch.setenv(env,secrets.token_urlsafe(40))
    monkeypatch.setattr(provision.psycopg,'connect',lambda *args,**kwargs:(_ for _ in ()).throw(provision.psycopg.OperationalError('PRIVATE')))
    with pytest.raises(SystemExit) as error:provision.main()
    assert 'PRIVATE' not in str(error.value) and capsys.readouterr()==('','')


def test_migration_and_schema_acl_contracts():
    roles=(ROOT/'database/roles.sql').read_text();grants=(ROOT/'database/permissions.sql').read_text()
    assert 'SECURITY DEFINER' not in roles+grants
    assert 'GRANT SELECT ON accounts,transfers,ledger_entries,flyway_schema_history TO bankops_reconciliation' in grants
    assert 'ALTER ROLE bankops_agent NOLOGIN' in roles and 'ALTER ROLE bankops_monitoring NOLOGIN' in roles
    assert 'ALTER DEFAULT PRIVILEGES FOR ROLE bankops_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC' in roles
    assert 'REVOKE ALL (%s)' in grants
    assert not any(word in roles+grants for word in ('UPDATE accounts SET','INSERT INTO accounts','DELETE FROM accounts','DISABLE TRIGGER','DROP TABLE'))
    config=yaml.safe_load((ROOT/'backend/banking-service/src/main/resources/application-db-secure.yaml').read_text())
    assert config['spring']['flyway']['enabled'] is False and config['bankops']['database']['verify-runtime'] is True


def test_monitoring_network_and_no_database_credentials():
    config=yaml.safe_load((ROOT/'compose.yaml').read_text())
    postgres=config['services']['postgres']
    assert 'BANKOPS_POSTGRES_ADMIN_PASSWORD' in postgres['environment']['POSTGRES_PASSWORD']
    assert 'scram-sha-256' in postgres['environment']['POSTGRES_INITDB_ARGS']
    assert './database/pg_hba.conf:/etc/postgresql/bankops-pg_hba.conf:ro' in postgres['volumes']
    rules=(ROOT/'database/pg_hba.conf').read_text().splitlines()
    active=[line.split() for line in rules if line and not line.startswith('#')]
    assert all(row[-1] in ('scram-sha-256','reject') for row in active)
    assert active[-1]==['host','all','all','::/0','reject']
    assert postgres['ports']==['127.0.0.1:5433:5432']
    for name in ('prometheus','grafana','jaeger'):
        service=config['services'][name];assert service['networks']==['monitoring']
        assert not any('POSTGRES' in key or key.startswith('BANKOPS_DB') for key in service.get('environment',{}))
    assert 'networks' not in postgres
    # The agent's persistent store is separate SQLite; no PostgreSQL driver/config.
    source=(ROOT/'agent/src/bankops_agent/config.py').read_text()
    assert 'BANKOPS_DB_PASSWORD' not in source and 'BANKOPS_RECONCILIATION_DSN' not in source
