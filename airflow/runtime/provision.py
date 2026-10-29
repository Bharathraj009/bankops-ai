"""Legacy SELECT-role setup; see database/README.md for the full ACL policy.

Never print credentials or touch banking rows. Existing-volume rollout is explicit.
"""
from pathlib import Path
import os
import secrets
import subprocess


def main():
    path = Path(__file__).resolve().parents[1] / '.env.local'
    names = ('BANKOPS_AIRFLOW_METADATA_PASSWORD','BANKOPS_AIRFLOW_UI_PASSWORD',
             'BANKOPS_RECONCILIATION_PASSWORD','BANKOPS_AIRFLOW_JWT_SECRET','BANKOPS_AIRFLOW_VIEWER_PASSWORD',
             'BANKOPS_AIRFLOW_METADATA_ADMIN_PASSWORD')
    values = {}
    if path.exists():
        values = dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line)
    for name in names:
        values[name] = os.environ.get(name) or values.get(name) or secrets.token_urlsafe(40)
    # Passwords are sent over stdin, not process arguments or tool output.
    password = values['BANKOPS_RECONCILIATION_PASSWORD'].replace("'","''")
    statement = """BEGIN;
SET LOCAL log_statement=none;
SET LOCAL log_min_error_statement=panic;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='bankops_reconciliation') THEN
CREATE ROLE bankops_reconciliation LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
END IF; END $$;
ALTER ROLE bankops_reconciliation PASSWORD '""" + password + """';
ALTER ROLE bankops_reconciliation IN DATABASE bankops SET default_transaction_read_only=on;
GRANT CONNECT ON DATABASE bankops TO bankops_reconciliation;
GRANT USAGE ON SCHEMA public TO bankops_reconciliation;
GRANT SELECT ON public.accounts, public.transfers, public.ledger_entries, public.flyway_schema_history TO bankops_reconciliation;
DO $$ BEGIN
IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='bankops_reconciliation' AND
 (rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls OR NOT rolcanlogin))
 OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='bankops_reconciliation'))
 OR has_schema_privilege('bankops_reconciliation','public','CREATE')
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p') AND
 has_table_privilege('bankops_reconciliation',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')) THEN
 RAISE EXCEPTION 'Role is not strictly read only';
END IF; END $$;
COMMIT;
"""
    result = subprocess.run(['docker','exec','-i','bankops-ai-postgres-1','psql','-X','-q','-U','bankops','-d','bankops','-v','ON_ERROR_STOP=1'],input=statement,text=True,capture_output=True)
    if result.returncode:
        raise SystemExit('Local role provisioning failed; details suppressed')
    path.write_text(''.join(name+'='+values[name]+'\n' for name in names))
    print('Local credentials stored in ignored .env.local; SELECT role provisioned; no banking rows changed')


if __name__ == '__main__': main()
