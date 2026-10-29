"""Actual-role denial probes and memory-only corruption; disposable target only."""

import hashlib
import json
import os
from decimal import Decimal


def controlled_mismatches(data, evaluate):
    """Never mutate the original snapshot or execute corrupting SQL."""
    accounts, transfers, entries = data
    changed = list(accounts)
    row = changed[0]
    changed[0] = (row[0], row[1], row[2] + Decimal("1.00"), row[3])
    cases = [
        ("balance", (changed, transfers, entries)),
        ("missing_posting", (accounts, transfers, entries[:-1])),
        ("duplicate_posting", (accounts, transfers, entries + entries[:1])),
        (
            "invalid_lifecycle",
            (accounts, [transfers[0][:-1] + ("FAILED",)] + transfers[1:], entries),
        ),
    ]
    for name, snapshot in cases:
        assert any(c.status == "FAIL" for c in evaluate(*snapshot)), name
    assert all(c.status == "PASS" for c in evaluate(*data))
    return [name for name, _ in cases]


def main():
    import psycopg

    from reconciliation import evaluate, reconcile

    assert os.environ.get("BANKOPS_SECURITY_E2E") == "step66-isolated"
    admin_dsn = os.environ["BANKOPS_DB_ADMIN_DSN"]
    args = psycopg.conninfo.conninfo_to_dict(admin_dsn)
    assert args["port"] == "55466" and args["dbname"] == "bankops"
    queries = (
        "SELECT id,currency,balance,opening_balance FROM accounts ORDER BY id",
        "SELECT id,source_account_id,destination_account_id,amount,currency,status FROM transfers ORDER BY id",
        "SELECT id,transfer_id,account_id,entry_type,amount,currency FROM ledger_entries ORDER BY id",
    )

    def snapshot():
        with psycopg.connect(admin_dsn) as c:
            c.execute("SET TRANSACTION READ ONLY")
            data = [c.execute(q).fetchall() for q in queries]
            c.rollback()
            return data

    before = snapshot()
    assert before[2], "Browser/API workflow must create real postings before verification"
    passwords = {
        "bankops_runtime": os.environ["BANKOPS_DB_PASSWORD"],
        "bankops_reconciliation": os.environ["BANKOPS_RECONCILIATION_PASSWORD"],
    }
    attempts = 0

    def denied(role, statement):
        nonlocal attempts
        params = args | {"user": role, "password": passwords[role]}
        with psycopg.connect(**params) as c:
            c.execute("SET TRANSACTION READ WRITE")
            try:
                c.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                attempts += 1
            else:
                raise AssertionError("Unauthorized operation allowed")
            finally:
                c.rollback()

    for statement in (
        "CREATE TABLE public.forbidden(id int)",
        "CREATE SCHEMA forbidden",
        "CREATE TEMP TABLE forbidden(id int)",
        "ALTER TABLE accounts DISABLE TRIGGER ALL",
        "SET session_replication_role=replica",
        "SET ROLE bankops_migrator",
        "SELECT * FROM flyway_schema_history",
        "UPDATE customer_account_ownership SET customer_id=customer_id WHERE false",
    ):
        denied("bankops_runtime", statement)
    for table in ("accounts", "transfers", "ledger_entries"):
        for statement in (
            f"INSERT INTO {table} DEFAULT VALUES",
            f"UPDATE {table} SET id=id WHERE false",
            f"DELETE FROM {table} WHERE false",
        ):
            denied("bankops_reconciliation", statement)
    for statement in (
        "SELECT * FROM customer_sessions",
        "SELECT * FROM customers",
        "SELECT create_idempotent_transfer('x','x','x',gen_random_uuid(),gen_random_uuid(),1,'USD')",
    ):
        denied("bankops_reconciliation", statement)
    reader = psycopg.conninfo.make_conninfo(
        **(
            args
            | {"user": "bankops_reconciliation", "password": passwords["bankops_reconciliation"]}
        )
    )
    try:
        psycopg.connect(
            **(
                args
                | {
                    "user": "bankops_runtime",
                    "password": passwords["bankops_runtime"],
                    "dbname": "postgres",
                }
            )
        )
    except psycopg.OperationalError:
        pass
    else:
        raise AssertionError("HBA allowed access to another database")
    result = reconcile(reader)
    assert result.status == "PASS"
    for role in ("bankops_agent", "bankops_monitoring"):
        with psycopg.connect(admin_dsn) as c:
            assert c.execute(
                "SELECT NOT rolcanlogin FROM pg_roles WHERE rolname=%s", (role,)
            ).fetchone()[0]
            c.execute("SET ROLE " + role)
            try:
                c.execute("UPDATE public.accounts SET balance=balance WHERE false")
            except psycopg.errors.InsufficientPrivilege:
                attempts += 1
            else:
                raise AssertionError("Disabled service role obtained write access")
            finally:
                c.rollback()
    # This intentional attempt is on a synthetic account, and must roll back.
    params = args | {"user": "bankops_runtime", "password": passwords["bankops_runtime"]}
    try:
        with psycopg.connect(**params) as c:
            c.execute("UPDATE accounts SET balance=balance+1 WHERE id=%s", (before[0][0][0],))
    except psycopg.errors.CheckViolation:
        pass
    else:
        raise AssertionError("Unmatched balance change committed")
    mutations = controlled_mismatches(before, evaluate)
    assert before == snapshot(), "Permission/reconciliation probes must preserve financial rows"
    # Expire only the generated test session; never touch financial records.
    with psycopg.connect(admin_dsn) as c:
        c.execute(
            "UPDATE customer_sessions SET created_at=CURRENT_TIMESTAMP-INTERVAL '2 seconds',"
            "expires_at=CURRENT_TIMESTAMP-INTERVAL '1 second' WHERE token_hash=%s",
            (os.environ["BANKOPS_SECURITY_EXPIRE_HASH"],),
        )
    print(
        json.dumps(
            {
                "acl_denials": attempts,
                "reconciliation": result.status,
                "controlled_memory_mismatches_detected": mutations,
                "financial_snapshot_unchanged": True,
                "snapshot_digest": hashlib.sha256(repr(before).encode()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
