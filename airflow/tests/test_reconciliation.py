from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import os

import psycopg
from psycopg import sql
import pytest

from reconciliation import evaluate, reconcile


@pytest.fixture
def database():
    dsn = os.environ.get('BANKOPS_RECONCILIATION_TEST_DSN')
    if not dsn:
        pytest.fail('Set BANKOPS_RECONCILIATION_TEST_DSN to disposable PostgreSQL')
    name = 'reconciliation_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    parameters = psycopg.conninfo.conninfo_to_dict(dsn) | {'dbname':name}
    target = psycopg.conninfo.make_conninfo(**parameters)
    try:
        yield target
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def schema(dsn, real=False):
    with psycopg.connect(dsn) as conn:
        if real:
            directory = Path(__file__).resolve().parents[2] / 'backend/banking-service/src/main/resources/db/migration'
            for version in range(1,6):
                conn.execute(next(directory.glob(f'V{version}__*.sql')).read_text(), prepare=False)
        else:
            # Deliberately corruptible synthetic schema; no production trigger is disabled.
            conn.execute('CREATE TABLE accounts(id uuid,currency text,balance numeric,opening_balance numeric); CREATE TABLE transfers(id uuid,source_account_id uuid,destination_account_id uuid,amount numeric,currency text,status text); CREATE TABLE ledger_entries(id uuid,transfer_id uuid,account_id uuid,entry_type text,amount numeric,currency text)', prepare=False)
        conn.execute('CREATE TABLE flyway_schema_history(version text,success boolean)')
        for version in range(1,6):
            conn.execute('INSERT INTO flyway_schema_history VALUES(%s,true)',(str(version),))


def seed(dsn, real=False):
    source, dest, transfer = uuid4(), uuid4(), uuid4()
    with psycopg.connect(dsn) as conn:
        if real:
            for identifier, opening in ((source, Decimal('1000.00')),(dest,Decimal('0.00'))):
                conn.execute('INSERT INTO accounts(id,account_number,balance) VALUES(%s,%s,%s)',(identifier,'SYNTHETIC-'+str(identifier),opening))
            conn.execute('INSERT INTO transfers(id,source_account_id,destination_account_id,amount) VALUES(%s,%s,%s,250.00)',(transfer,source,dest))
            for account, kind in ((source,'DEBIT'),(dest,'CREDIT')):
                conn.execute('INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount) VALUES(%s,%s,%s,%s,250.00)',(uuid4(),transfer,account,kind))
            conn.execute("UPDATE transfers SET status='COMPLETED' WHERE id=%s",(transfer,))
        else:
            conn.execute("INSERT INTO accounts VALUES(%s,'USD',750,1000),(%s,'USD',250,0)",(source,dest))
            conn.execute("INSERT INTO transfers VALUES(%s,%s,%s,250,'USD','COMPLETED')",(transfer,source,dest))
            for account, kind in ((source,'DEBIT'),(dest,'CREDIT')):
                conn.execute("INSERT INTO ledger_entries VALUES(%s,%s,%s,%s,250,'USD')",(uuid4(),transfer,account,kind))
    return source,dest,transfer


def test_real_v1_v5_and_opening_reserve(database):
    schema(database,real=True)
    seed(database,real=True)
    before = snapshot(database)
    result = reconcile(database)
    assert result.status == 'PASS' and all(c.violations == 0 for c in result.checks)
    assert result.started_at <= result.completed_at
    assert snapshot(database) == before


def snapshot(dsn):
    with psycopg.connect(dsn) as conn:
        return [conn.execute('SELECT row_to_json(t)::text FROM public.' + table + ' t ORDER BY id').fetchall() for table in ('accounts','transfers','ledger_entries')]


@pytest.mark.parametrize('mutation,rule',[
    ("DELETE FROM ledger_entries WHERE entry_type='CREDIT'",'completed_double_entry'),
    ("INSERT INTO ledger_entries SELECT * FROM ledger_entries WHERE entry_type='DEBIT'",'ledger_consistency'),
    ("UPDATE ledger_entries SET amount=249 WHERE entry_type='CREDIT'",'ledger_consistency'),
    ("UPDATE accounts SET balance=balance+0.01",'account_balances'),
    ("UPDATE transfers SET status='FAILED'",'lifecycle_ledger'),
    ("UPDATE transfers SET status='UNKNOWN'",'lifecycle_ledger'),
    ("UPDATE ledger_entries SET account_id=gen_random_uuid()",'ledger_consistency'),
    ("UPDATE ledger_entries SET transfer_id=gen_random_uuid()",'ledger_consistency'),
    ("UPDATE ledger_entries SET currency='EUR'",'ledger_consistency'),
    ("UPDATE ledger_entries SET entry_type='OTHER'",'ledger_consistency'),
    ("UPDATE accounts SET balance='NaN'",'account_balances'),
    ("UPDATE ledger_entries SET account_id=(SELECT source_account_id FROM transfers)",'ledger_consistency'),
    ("UPDATE ledger_entries SET amount=-1",'ledger_consistency'),
    ("UPDATE transfers SET currency='EUR'",'ledger_consistency'),
])
def test_corrupt_synthetic_snapshots(database,mutation,rule):
    schema(database)
    seed(database)
    with psycopg.connect(database) as conn: conn.execute(mutation)
    before = snapshot(database)
    result = reconcile(database)
    assert result.status == 'FAIL'
    assert next(c for c in result.checks if c.rule == rule).violations > 0
    assert snapshot(database) == before
    assert 'SYNTHETIC' not in str(result.to_dict())


def test_pending_postings_and_failed_without_postings(database):
    schema(database)
    seed(database)
    with psycopg.connect(database) as conn: conn.execute("UPDATE transfers SET status='PENDING'")
    assert reconcile(database).status == 'PASS'  # V2 permits a full pair while pending.
    with psycopg.connect(database) as conn:
        conn.execute('DELETE FROM ledger_entries')
        conn.execute('UPDATE accounts SET balance=opening_balance')
        conn.execute("UPDATE transfers SET status='FAILED'")
    assert reconcile(database).status == 'PASS'


def test_missing_schema_cap_and_empty(database):
    assert reconcile(database).status == 'INSUFFICIENT_DATA'
    schema(database)
    assert reconcile(database).status == 'PASS'
    seed(database)
    assert reconcile(database,max_rows=1).status == 'INSUFFICIENT_DATA'
    with psycopg.connect(database) as conn: conn.execute("DELETE FROM flyway_schema_history WHERE version='3'")
    assert reconcile(database).status == 'INSUFFICIENT_DATA'


def test_read_only_session_and_safe_failure(database,monkeypatch,capsys):
    schema(database,True)
    seed(database,True)
    original = psycopg.connect
    observed = []
    def connect(*args,**kwargs):
        conn = original(*args,**kwargs)
        if 'options' in kwargs:
            assert conn.execute('SHOW transaction_read_only').fetchone()[0] == 'on'
            conn.rollback()
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                conn.execute('DELETE FROM accounts')
            conn.rollback()
            observed.append(True)
        return conn
    monkeypatch.setattr(psycopg,'connect',connect)
    assert reconcile(database).status == 'PASS' and observed
    def timeout(*args,**kwargs): raise psycopg.OperationalError('PRIVATE credentials')
    monkeypatch.setattr(psycopg,'connect',timeout)
    result = reconcile(database)
    assert result.status == 'INSUFFICIENT_DATA' and not result.checks
    assert 'PRIVATE' not in str(result.to_dict())
    assert capsys.readouterr() == ('','')


def test_decimal_precision():
    source,dest,transfer = uuid4(),uuid4(),uuid4()
    amount = Decimal('99999999999999999.99')
    accounts = [(source,'USD',Decimal('0'),amount),(dest,'USD',amount,Decimal('0'))]
    transfers = [(transfer,source,dest,amount,'USD','COMPLETED')]
    entries = [(uuid4(),transfer,source,'DEBIT',amount,'USD'),(uuid4(),transfer,dest,'CREDIT',amount,'USD')]
    assert all(c.status == 'PASS' for c in evaluate(accounts,transfers,entries))


def test_single_snapshot_during_concurrent_commit(database,monkeypatch):
    schema(database)
    seed(database)
    original = psycopg.connect
    class SnapshotConnection:
        def __init__(self, conn): self.conn = conn
        def __enter__(self): self.conn.__enter__(); return self
        def __exit__(self,*args): return self.conn.__exit__(*args)
        def rollback(self): self.conn.rollback()
        def execute(self,query,*args,**kwargs):
            result = self.conn.execute(query,*args,**kwargs)
            if query.startswith('SELECT id,currency,balance'):
                with original(database) as writer:
                    writer.execute('UPDATE accounts SET balance=balance+1')
            return result
    def connect(*args,**kwargs):
        conn = original(*args,**kwargs)
        return SnapshotConnection(conn) if 'options' in kwargs else conn
    with monkeypatch.context() as patch:
        patch.setattr(psycopg,'connect',connect)
        assert reconcile(database).status == 'PASS'
    assert reconcile(database).status == 'FAIL'


def test_v6_reconciliation_with_real_select_only_login(database):
    import secrets
    schema(database,real=True)
    seed(database,real=True)
    before=snapshot(database)
    name='readonly_'+uuid4().hex
    password=secrets.token_urlsafe(40)
    with psycopg.connect(database) as admin:
        migration=next((Path(__file__).resolve().parents[2]/'backend/banking-service/src/main/resources/db/migration').glob('V6__*.sql'))
        admin.execute(migration.read_text(),prepare=False)
        admin.execute("INSERT INTO flyway_schema_history VALUES('6',true)")
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(name),sql.Literal(password)))
        admin.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(name)))
        admin.execute(sql.SQL('GRANT SELECT ON accounts,transfers,ledger_entries,flyway_schema_history TO {}').format(sql.Identifier(name)))
    target=psycopg.conninfo.conninfo_to_dict(database)|{'user':name,'password':password}
    result=reconcile(psycopg.conninfo.make_conninfo(**target))
    assert result.status=='PASS' and all(c.status=='PASS' for c in result.checks)
    assert snapshot(database)==before
    with psycopg.connect(**target) as reader:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):reader.execute('SELECT * FROM customer_sessions')
