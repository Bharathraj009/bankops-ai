"""Check only this fixture's isolated SQLite audit guards; every write is rolled back."""
import hashlib
import json
from pathlib import Path
import sqlite3

database=Path(__file__).resolve().parents[1]/'.cache'/'step61'/'governance.sqlite3'
if not database.exists():raise SystemExit('Isolated fixture database missing')
connection=sqlite3.connect(database)
def fingerprint():
    return hashlib.sha256('\n'.join(connection.iterdump()).encode()).hexdigest()
before=fingerprint()
attempts=0
for table in ('approval_audit','read_only_audit','execution_audit','verification_audit'):
    if connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0:raise SystemExit('Missing fixture audit')
    for statement in (f'UPDATE {table} SET event=event',f'DELETE FROM {table}'):
        connection.execute('BEGIN')
        try:
            connection.execute(statement)
        except sqlite3.IntegrityError:
            attempts+=1
        else:
            raise SystemExit('Audit mutation unexpectedly permitted')
        finally:
            connection.rollback()
after=fingerprint()
if before!=after:raise SystemExit('Fixture changed during audit guard verification')
counts={table:connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('proposals','read_only_proposals','remediation_executions','execution_verifications','approval_audit','read_only_audit','execution_audit','verification_audit')}
connection.close()
print(json.dumps({'audit_mutations_rejected':attempts,'all_attempts_rolled_back':True,'logical_database_unchanged':before==after,'counts':counts}))
