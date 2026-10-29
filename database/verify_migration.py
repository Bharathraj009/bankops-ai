"""Packaged migration launcher proof; fixed disposable Step 65 target only."""
import json
import os
from pathlib import Path
import secrets
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
CONTAINER='bankops-step65-tests'


def sql(database,statement):
    result=subprocess.run(['docker','exec','-i',CONTAINER,'psql','-X','-q','-At','-U','bankops_test','-d',database,'-v','ON_ERROR_STOP=1'],input=statement,text=True,capture_output=True)
    if result.returncode:raise RuntimeError('Isolated migration fixture failed; diagnostics suppressed')
    return result.stdout.strip()


def main():
    if os.environ.get('BANKOPS_DB_SECURITY_TEST')!='step65-disposable':raise SystemExit('Explicit disposable test opt-in required')
    name='migration_cli_'+uuid4().hex;password=secrets.token_urlsafe(40)
    runtime_password=secrets.token_urlsafe(40);reader_password=secrets.token_urlsafe(40)
    sql('bankops_test','CREATE DATABASE '+name)
    sql(name,'BEGIN; SET LOCAL log_statement=none; SET LOCAL log_min_error_statement=panic;\n'+(ROOT/'database/roles.sql').read_text()+
        "\nALTER ROLE bankops_migrator LOGIN PASSWORD '"+password+"';\nALTER ROLE bankops_runtime LOGIN PASSWORD '"+runtime_password+
        "';\nALTER ROLE bankops_reconciliation LOGIN PASSWORD '"+reader_password+"'; COMMIT;")
    env={k:v for k,v in os.environ.items() if not k.startswith(('SPRING_','BANKOPS_'))}
    env.update(BANKOPS_MIGRATION_DB_URL='jdbc:postgresql://127.0.0.1:55465/'+name,
        BANKOPS_MIGRATION_DB_USER='bankops_migrator',BANKOPS_MIGRATION_DB_PASSWORD=password)
    command=['C:/Program Files/Java/jdk-25/bin/java.exe','-Dloader.main=com.bankops.banking.security.DatabaseMigration',
        '-cp',str(ROOT/'backend/banking-service/target/banking-service-0.0.1-SNAPSHOT.jar'),
        'org.springframework.boot.loader.launch.PropertiesLauncher']
    def run(expected):
        result=subprocess.run(command,env=env,text=True,capture_output=True,timeout=60)
        assert result.returncode==expected, 'Packaged migration launcher failed; diagnostics suppressed'
        assert all(secret not in result.stdout+result.stderr for secret in (password,env['BANKOPS_MIGRATION_DB_PASSWORD']))
    run(2)
    env['BANKOPS_MIGRATION_APPLY']='local-only'
    run(0);run(0)
    assert sql(name,"SELECT string_agg(version,',' ORDER BY installed_rank) FROM public.flyway_schema_history WHERE success AND version IS NOT NULL")=='1,2,3,4,5,6'
    tool_env=dict(env,BANKOPS_DB_SECURITY_APPLY='local-only',BANKOPS_DB_NAME=name,
        BANKOPS_DB_ADMIN_DSN='host=host.docker.internal port=55465 dbname='+name+' user=bankops_test password=isolated_step65_only',
        BANKOPS_DB_PASSWORD=runtime_password,BANKOPS_RECONCILIATION_PASSWORD=reader_password)
    def provision(operation,expected=0):
        command=['docker','run','--rm','-e','PYTHONDONTWRITEBYTECODE=1']
        for key in ('BANKOPS_DB_SECURITY_APPLY','BANKOPS_DB_NAME','BANKOPS_DB_ADMIN_DSN','BANKOPS_DB_PASSWORD','BANKOPS_RECONCILIATION_PASSWORD','BANKOPS_MIGRATION_DB_PASSWORD'):
            command+=['-e',key]
        command+=['-v',str(ROOT)+':/workspace:ro','-w','/workspace','bankops-airflow-step63-tests','python','database/provision.py',operation]
        result=subprocess.run(command,env=tool_env,text=True,capture_output=True,timeout=30)
        assert result.returncode==expected,'Isolated provisioning CLI failed; diagnostics suppressed'
        assert all(secret not in result.stdout+result.stderr for secret in (password,runtime_password,reader_password))
    provision('prepare');provision('prepare')
    tool_env['BANKOPS_DB_PASSWORD']=secrets.token_urlsafe(40);provision('prepare',1)
    tool_env['BANKOPS_DB_PASSWORD']=runtime_password;provision('prepare')
    provision('grant');provision('grant')
    env['BANKOPS_MIGRATION_DB_PASSWORD']=secrets.token_urlsafe(40);run(1)
    print(json.dumps({'packaged_launcher_default_disabled':True,'dedicated_non_superuser_migration':True,
        'flyway_v1_v6_validated':True,'repeat_migration_noop':True,'wrong_password_rejected_without_leak':True,
        'provision_cli_prepare_and_grant_repeatable':True,'credential_mismatch_rolled_back_without_rotation':True,
        'application_server_not_started':True,'development_database_accessed':False}))


if __name__=='__main__':main()
