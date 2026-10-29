"""Assemble credential-bearing URLs in memory; never print them."""
import json
import os
from pathlib import Path
from urllib.parse import quote

from psycopg.conninfo import make_conninfo


def configure():
    password = os.environ['BANKOPS_AIRFLOW_METADATA_PASSWORD']
    os.environ['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'] = 'postgresql+psycopg2://airflow:' + quote(password,safe='') + '@airflow-metadata:5432/airflow'
    host = os.environ.get('BANKOPS_RECONCILIATION_HOST', 'bankops-ai-postgres-1')
    if host not in ('postgres', 'bankops-ai-postgres-1'):
        raise ValueError('Unsupported local reconciliation host')
    os.environ['BANKOPS_RECONCILIATION_DSN'] = make_conninfo(host=host,port=5432,dbname='bankops',
        user='bankops_reconciliation',password=os.environ['BANKOPS_RECONCILIATION_PASSWORD'])
    path = Path('/opt/airflow/local-auth/passwords.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    # Preseed the dev auth manager so it never generates/prints a password.
    passwords = {'localadmin':os.environ['BANKOPS_AIRFLOW_UI_PASSWORD']}
    if os.environ.get('BANKOPS_AIRFLOW_VIEWER_PASSWORD'):
        passwords['agentviewer'] = os.environ['BANKOPS_AIRFLOW_VIEWER_PASSWORD']
    path.write_text(json.dumps(passwords))
    path.chmod(0o600)


if __name__ == '__main__':
    configure()
    os.execvp('airflow',['airflow','standalone'])
