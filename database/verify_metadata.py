"""Opt-in proof against the fixed disposable Step 65 metadata container only."""
import json
import os
import subprocess

CONTAINER='bankops-step65-metadata'


def query(user,password_variable,statement):
    command=['docker','exec','-i',CONTAINER,'sh','-c',
        'export PGPASSWORD="$'+password_variable+'"; exec psql -X -h 127.0.0.1 -U '+user+' -d airflow -v ON_ERROR_STOP=1 -At']
    result=subprocess.run(command,input=statement,text=True,capture_output=True)
    if result.returncode:raise RuntimeError('Isolated metadata verification failed; diagnostics suppressed')
    return result.stdout.strip()


def main():
    if os.environ.get('BANKOPS_DB_SECURITY_TEST')!='step65-disposable':raise SystemExit('Explicit disposable test opt-in required')
    assert query('airflow_admin','POSTGRES_PASSWORD',"SELECT NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls) AND rolcanlogin FROM pg_roles WHERE rolname='airflow';")=='t'
    query('airflow','BANKOPS_AIRFLOW_METADATA_PASSWORD',"""
        BEGIN; CREATE TABLE public.synthetic_metadata(id int); INSERT INTO public.synthetic_metadata VALUES(1);
        DO $$ BEGIN
            BEGIN CREATE ROLE forbidden_metadata_role; RAISE EXCEPTION 'Privilege unexpectedly allowed';
            EXCEPTION WHEN insufficient_privilege THEN NULL; END;
        END $$;
        ROLLBACK;
        """)
    env=json.loads(subprocess.check_output(['docker','inspect',CONTAINER],text=True))[0]['Config']['Env']
    secrets=[v.split('=',1)[1] for v in env if v.startswith(('POSTGRES_PASSWORD=','BANKOPS_AIRFLOW_METADATA_PASSWORD='))]
    result=subprocess.run(['docker','logs',CONTAINER],text=True,capture_output=True)
    assert all(secret not in result.stdout+result.stderr for secret in secrets)
    print(json.dumps({'metadata_runtime_not_superuser':True,'metadata_migrations_and_dml_allowed':True,
        'cluster_role_creation_denied':True,'verification_transaction_rolled_back':True,'credentials_absent_from_container_logs':True}))


if __name__=='__main__':main()
