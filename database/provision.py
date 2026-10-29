"""Explicit environment ACL provisioning. No banking DML or credential output.

Run with psycopg installed, as an infrastructure administrator. prepare creates
bounded roles and sets SCRAM verifiers; grant applies reviewed post-migration ACLs.
Does not reassign existing objects, rotate existing passwords implicitly, or print
SQL/provider errors. Store unique credentials in the caller's environment.
"""
import argparse
import base64
import hashlib
import hmac
import os
from pathlib import Path
import secrets

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent
PASSWORDS = {
    'bankops_migrator': 'BANKOPS_MIGRATION_DB_PASSWORD',
    'bankops_runtime': 'BANKOPS_DB_PASSWORD',
    'bankops_reconciliation': 'BANKOPS_RECONCILIATION_PASSWORD',
}


def scram(password):
    """PostgreSQL SCRAM-SHA-256 verifier; plaintext never enters SQL."""
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac('sha256', password.encode('ascii'), salt, 4096)
    client = hmac.digest(salted, b'Client Key', 'sha256')
    stored = hashlib.sha256(client).digest()
    server = hmac.digest(salted, b'Server Key', 'sha256')
    enc = lambda value: base64.b64encode(value).decode('ascii')
    return f'SCRAM-SHA-256$4096:{enc(salt)}${enc(stored)}:{enc(server)}'


def prepare(connection, passwords):
    if set(passwords) != set(PASSWORDS) or len(set(passwords.values())) != 3:
        raise ValueError('Three distinct role credentials are required')
    if any(not 32 <= len(p) <= 256 or not p.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in p) for p in passwords.values()):
        raise ValueError('Role credentials require 32-256 printable ASCII characters')
    ensure_no_runtime_ownership(connection)
    # No password/verifier SQL is emitted even when cluster statement logging is enabled.
    connection.execute("SET LOCAL log_statement='none'")
    connection.execute("SET LOCAL log_min_error_statement='panic'")
    connection.execute((ROOT / 'roles.sql').read_text(), prepare=False)
    for role, password in passwords.items():
        # Avoid accidentally rotating a live role during a repeat execution.
        existing = connection.execute('SELECT rolpassword FROM pg_authid WHERE rolname=%s', (role,)).fetchone()[0]
        if existing:
            algorithm, rounds_salt, keys = existing.split('$')
            rounds, salt = rounds_salt.split(':')
            if algorithm != 'SCRAM-SHA-256' or int(rounds) != 4096:
                raise ValueError('Existing verifier requires a reviewed credential rollout')
            salted = hashlib.pbkdf2_hmac('sha256', password.encode('ascii'), base64.b64decode(salt), int(rounds))
            expected = base64.b64encode(hashlib.sha256(hmac.digest(salted,b'Client Key','sha256')).digest()).decode('ascii')
            if not hmac.compare_digest(expected, keys.split(':')[0]):
                raise ValueError('Existing credentials differ; rotation requires a separate reviewed rollout')
            connection.execute(sql.SQL('ALTER ROLE {} LOGIN').format(sql.Identifier(role)))
        else:
            connection.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(scram(password))))


def ensure_no_runtime_ownership(connection):
    if connection.execute("""SELECT EXISTS(SELECT 1 FROM (
        SELECT datdba AS owner FROM pg_database WHERE datname=current_database()
        UNION ALL SELECT nspowner FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname<>'information_schema'
        UNION ALL SELECT relowner FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
        UNION ALL SELECT proowner FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
        ) objects JOIN pg_roles r ON r.oid=objects.owner WHERE r.rolname IN
        ('bankops_runtime','bankops_reconciliation','bankops_agent','bankops_monitoring'))""").fetchone()[0]:
        raise ValueError('Unsafe object ownership requires a separate reviewed rollout')


def grant(connection):
    connection.execute("SET LOCAL search_path=pg_catalog,public")
    # Fail atomically on an incomplete schema. V6 customer metadata is required.
    if not {'1','2','3','4','5','6'} <= {r[0] for r in connection.execute('SELECT version FROM public.flyway_schema_history WHERE success')}:
        raise ValueError('Migrate and validate V1-V6 first')
    # Runtime/reader/disabled principals must not own objects, or REVOKE is ineffective.
    ensure_no_runtime_ownership(connection)
    connection.execute((ROOT / 'roles.sql').read_text(), prepare=False)
    connection.execute((ROOT / 'permissions.sql').read_text(), prepare=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare','grant'))
    operation = parser.parse_args().operation
    if os.environ.get('BANKOPS_DB_SECURITY_APPLY') != 'local-only':
        raise SystemExit('Explicit local database-security opt-in required')
    try:
        name = os.environ['BANKOPS_DB_NAME']
        target = psycopg.conninfo.conninfo_to_dict(os.environ['BANKOPS_DB_ADMIN_DSN'])
        if target.get('host') not in ('127.0.0.1','localhost','::1','host.docker.internal'):
            raise ValueError('Only explicit local database hosts are supported')
        if operation == 'prepare' and target.get('password') in [os.environ[env] for env in PASSWORDS.values()]:
            raise ValueError('Administrator and service credentials must differ')
        with psycopg.connect(os.environ['BANKOPS_DB_ADMIN_DSN'], connect_timeout=5) as connection:
            if connection.execute('SELECT current_database()').fetchone()[0] != name:
                raise ValueError('Database target mismatch')
            if operation == 'prepare':
                prepare(connection, {role: os.environ[env] for role, env in PASSWORDS.items()})
            else:
                grant(connection)
        print('Database role configuration committed; no banking records changed')
    except (psycopg.Error, ValueError, KeyError):
        raise SystemExit('Database role configuration failed; transaction rolled back; details suppressed') from None


if __name__ == '__main__':
    main()
