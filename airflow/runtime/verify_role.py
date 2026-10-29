"""Verify the dedicated development role with harmless denied operations."""
from pathlib import Path
import json
import psycopg
from reconciliation import reconcile

values = dict(line.split('=',1) for line in (Path(__file__).resolve().parents[1] / '.env.local').read_text().splitlines() if '=' in line)
dsn = psycopg.conninfo.make_conninfo(host='127.0.0.1',port=5433,dbname='bankops',user='bankops_reconciliation',password=values['BANKOPS_RECONCILIATION_PASSWORD'])
with psycopg.connect(dsn) as conn:
    readonly = conn.execute('SHOW transaction_read_only').fetchone()[0]
    conn.rollback()
    permissions = conn.execute("SELECT has_table_privilege(current_user,'public.'||t,'SELECT'), has_table_privilege(current_user,'public.'||t,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER') FROM unnest(ARRAY['accounts','transfers','ledger_entries','flyway_schema_history']) t").fetchall()
    conn.rollback()
    assert readonly == 'on' and all(select and not write for select,write in permissions)
    # Even if a session switches read-only off, ACL denies a zero-row DELETE.
    conn.execute('SET TRANSACTION READ WRITE')
    try:
        conn.execute('DELETE FROM public.accounts WHERE false')
        raise AssertionError('Write permission unexpectedly granted')
    except psycopg.errors.InsufficientPrivilege:
        conn.rollback()
result = reconcile(dsn)
print(json.dumps({'role_default_read_only':readonly,'select_only_all_four_tables':True,'zero_row_write_denied_by_acl':True,'direct_reconciliation':result.to_dict()}))
