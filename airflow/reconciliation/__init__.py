"""Read-only, privacy-preserving banking reconciliation."""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext
import os

import psycopg


@dataclass(frozen=True)
class Check:
    rule: str
    status: str
    violations: int


@dataclass(frozen=True)
class Result:
    started_at: str
    completed_at: str
    status: str
    reason: str
    checks: tuple[Check, ...]

    def to_dict(self):
        return asdict(self)


def money(value):
    return isinstance(value, Decimal) and value.is_finite() and value >= 0 and value == value.quantize(Decimal('0.01'))


def evaluate(accounts, transfers, entries):
    """Pure deterministic rules; identifiers stay internal and never enter results."""
    account_map = {a[0]: a for a in accounts}
    transfer_map = {t[0]: t for t in transfers}
    grouped = defaultdict(list)
    deltas = defaultdict(lambda: Decimal('0'))
    violations = Counter()
    with localcontext() as context:
        context.prec = 80  # Exact sums for bounded NUMERIC(19,2) rows.
        for entry_id, transfer_id, account_id, kind, amount, currency in entries:
            grouped[transfer_id].append((account_id, kind, amount, currency))
            valid = money(amount) and amount > 0 and currency == 'USD' and kind in ('DEBIT','CREDIT')
            if not valid or transfer_id not in transfer_map or account_id not in account_map:
                violations['ledger_consistency'] += 1
            if valid:
                deltas[account_id] += amount if kind == 'CREDIT' else -amount
        ids = Counter(row[0] for row in entries)
        violations['ledger_consistency'] += sum(count - 1 for count in ids.values())
        for identifier, source, destination, amount, currency, status in transfers:
            postings = grouped[identifier]
            valid_transfer = (source in account_map and destination in account_map and source != destination
                and money(amount) and amount > 0 and currency == 'USD')
            valid_pair = (valid_transfer and len(postings) == 2
                and Counter((p[0], p[1]) for p in postings) == Counter(((source,'DEBIT'),(destination,'CREDIT')))
                and all(money(p[2]) and p[2] == amount and p[3] == currency for p in postings))
            if status == 'COMPLETED' and not valid_pair:
                violations['completed_double_entry'] += 1
            if not valid_transfer or (postings and not valid_pair):
                violations['ledger_consistency'] += 1
            if status not in ('PENDING','COMPLETED','FAILED') or (status == 'FAILED' and postings) or (status == 'COMPLETED' and not valid_pair):
                violations['lifecycle_ledger'] += 1
        for identifier, currency, balance, opening in accounts:
            if currency != 'USD' or not money(balance) or not money(opening) or balance != opening + deltas[identifier]:
                violations['account_balances'] += 1
    return tuple(Check(rule, 'FAIL' if violations[rule] else 'PASS', violations[rule]) for rule in
        ('completed_double_entry','account_balances','ledger_consistency','lifecycle_ledger'))


def reconcile(dsn=None, *, max_rows=100000):
    started = datetime.now(UTC).isoformat()
    checks = ()
    status, reason = 'INSUFFICIENT_DATA', 'source_unavailable_or_incompatible'
    try:
        if not isinstance(max_rows, int) or isinstance(max_rows, bool) or not 1 <= max_rows <= 100000:
            raise ValueError('Invalid bound')
        dsn = dsn if dsn is not None else os.environ.get('BANKOPS_RECONCILIATION_DSN')
        if not dsn:
            raise ValueError('Missing configuration')
        with psycopg.connect(dsn, connect_timeout=5, options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=2000') as connection:
            # One consistent committed snapshot. Always roll back, even on success.
            try:
                connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                versions = connection.execute('SELECT version FROM public.flyway_schema_history WHERE success AND version IS NOT NULL').fetchall()
                if not {'1','2','3','4','5'} <= {v[0] for v in versions}:
                    raise ValueError('Unsupported schema')
                data = []
                for query in (
                    'SELECT id,currency,balance,opening_balance FROM public.accounts',
                    'SELECT id,source_account_id,destination_account_id,amount,currency,status FROM public.transfers',
                    'SELECT id,transfer_id,account_id,entry_type,amount,currency FROM public.ledger_entries'):
                    rows = connection.execute(query + ' LIMIT %s', (max_rows + 1,)).fetchall()
                    if len(rows) > max_rows:
                        raise ValueError('Incomplete snapshot')
                    data.append(rows)
                checks = evaluate(*data)
                status = 'FAIL' if any(check.status == 'FAIL' for check in checks) else 'PASS'
                reason = 'snapshot_checked'
            finally:
                connection.rollback()
    except (psycopg.Error, ValueError, ArithmeticError, TypeError):
        # Never log SQL errors, connection strings, account identifiers or values.
        pass
    return Result(started, datetime.now(UTC).isoformat(), status, reason, checks)
