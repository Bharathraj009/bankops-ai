"""Verify SCRAM and database isolation on fixed disposable HBA test container."""
import json
import os
from pathlib import Path
import subprocess

CONTAINER='bankops-step65-hba'


def query(user,database,variable,statement):
    return subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c',
        'export PGPASSWORD="$'+variable+'"; exec psql -X -h 127.0.0.1 -U '+user+' -d '+database+' -v ON_ERROR_STOP=1 -At'],input=statement,text=True,capture_output=True)


def main():
    if os.environ.get('BANKOPS_DB_SECURITY_TEST')!='step65-disposable':raise SystemExit('Explicit disposable test opt-in required')
    statement='BEGIN; SET LOCAL log_statement=none; SET LOCAL log_min_error_statement=panic;\n'
    statement+=(Path(__file__).parent/'roles.sql').read_text()
    statement+="\n\\getenv password BANKOPS_DB_PASSWORD\nALTER ROLE bankops_runtime LOGIN PASSWORD :'password'; COMMIT;"
    assert query('bankops','bankops','POSTGRES_PASSWORD',statement).returncode==0, 'Isolated HBA setup failed'
    assert query('bankops_runtime','bankops','BANKOPS_DB_PASSWORD','SELECT current_user;').stdout.strip()=='bankops_runtime'
    assert query('bankops_runtime','postgres','BANKOPS_DB_PASSWORD','SELECT 1;').returncode!=0
    assert query('bankops_runtime','bankops','POSTGRES_PASSWORD','SELECT 1;').returncode!=0
    assert query('bankops','bankops','POSTGRES_PASSWORD',"SELECT count(*) FROM pg_hba_file_rules WHERE auth_method='trust' OR error IS NOT NULL;").stdout.strip()=='0'
    env=json.loads(subprocess.check_output(['docker','inspect',CONTAINER],text=True))[0]['Config']['Env']
    passwords=[v.split('=',1)[1] for v in env if v.startswith(('POSTGRES_PASSWORD=','BANKOPS_DB_PASSWORD='))]
    logs=subprocess.run(['docker','logs',CONTAINER],text=True,capture_output=True)
    assert all(value not in logs.stdout+logs.stderr for value in passwords)
    print(json.dumps({'scram_login_succeeded':True,'wrong_password_denied':True,'other_database_connection_denied':True,
        'no_trust_or_invalid_hba_rules':True,'credentials_absent_from_logs':True}))


if __name__=='__main__':main()
