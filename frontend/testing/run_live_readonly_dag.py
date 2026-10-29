"""Explicit operator-only one-run verification, piped into the local Airflow container.

Never called by the UI or agent. Persists an exclusive claim before running;
failure requires inspection, never an automatic retry. No financial DML.
"""
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from urllib.parse import quote

password = os.environ['BANKOPS_AIRFLOW_METADATA_PASSWORD']
os.environ['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'] = (
    'postgresql+psycopg2://airflow:' + quote(password, safe='') + '@airflow-metadata:5432/airflow')
import psycopg

dsn = psycopg.conninfo.make_conninfo(host='bankops-ai-postgres-1', port=5432,
    dbname='bankops', user='bankops_reconciliation',
    password=os.environ['BANKOPS_RECONCILIATION_PASSWORD'])
os.environ['BANKOPS_RECONCILIATION_DSN'] = dsn
with psycopg.connect(dsn) as connection:
    readonly = connection.execute('SHOW transaction_read_only').fetchone()[0]
    permissions = connection.execute("""SELECT has_table_privilege(current_user,'public.'||t,'SELECT'),
        has_table_privilege(current_user,'public.'||t,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
        FROM unnest(ARRAY['accounts','transfers','ledger_entries','flyway_schema_history']) t""").fetchall()
    connection.rollback()
    assert readonly == 'on' and all(select and not write for select, write in permissions)
print(json.dumps({'role_default_read_only': True, 'select_only_all_four_tables': True}), flush=True)

# A persistent exclusive claim also prevents accidental rerun after a failed CLI.
claim = Path('/opt/airflow/local-auth/step62-live-20261027.claim')
logical_date = datetime.now(UTC).isoformat()
with claim.open('x') as stream:
    json.dump({'logical_date': logical_date, 'purpose': 'one_read_only_dashboard_verification'}, stream)

from airflow.cli.cli_parser import get_parser
args = get_parser().parse_args(['dags', 'test', 'bankops_daily_reconciliation', logical_date])
args.func(args)
