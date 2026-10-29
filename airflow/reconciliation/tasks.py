"""Bounded task payloads and safe failure messages; no banking writes."""
from datetime import datetime
import json
import logging
import os

from airflow.exceptions import AirflowException
from airflow.sdk.exceptions import AirflowFailException
import psycopg

from reconciliation import reconcile

RULES = {'completed_double_entry','account_balances','ledger_consistency','lifecycle_ledger'}


def validate_connectivity():
    dsn = os.environ.get('BANKOPS_RECONCILIATION_DSN')
    if not dsn:
        raise AirflowException('Reconciliation connectivity unavailable')
    try:
        with psycopg.connect(dsn, connect_timeout=5, options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=2000') as connection:
            try:
                connection.execute('SET TRANSACTION READ ONLY')
                if connection.execute('SHOW transaction_read_only').fetchone()[0] != 'on':
                    raise ValueError('Read-only required')
                connection.execute('SELECT 1').fetchone()
            finally:
                connection.rollback()
    except (psycopg.Error, ValueError, TypeError):
        raise AirflowException('Reconciliation connectivity unavailable') from None


def safe_result(value):
    """Strict aggregate contract; reject rather than echo arbitrary XCom content."""
    try:
        if set(value) != {'started_at','completed_at','status','reason','checks'}:
            raise ValueError()
        if value['status'] not in ('PASS','FAIL','INSUFFICIENT_DATA'):
            raise ValueError()
        if value['reason'] not in ('snapshot_checked','source_unavailable_or_incompatible'):
            raise ValueError()
        for field in ('started_at','completed_at'):
            if not isinstance(value[field],str) or len(value[field]) > 40 or datetime.fromisoformat(value[field]).utcoffset() is None:
                raise ValueError()
        if datetime.fromisoformat(value['completed_at']) < datetime.fromisoformat(value['started_at']):
            raise ValueError()
        checks = value['checks']
        if not isinstance(checks,(list,tuple)) or len(checks) > 4:
            raise ValueError()
        seen = set()
        for check in checks:
            if set(check) != {'rule','status','violations'} or check['rule'] not in RULES or check['rule'] in seen:
                raise ValueError()
            seen.add(check['rule'])
            count = check['violations']
            if type(count) is not int or not 0 <= count <= 1000000 or check['status'] != ('FAIL' if count else 'PASS'):
                raise ValueError()
        if value['status'] == 'INSUFFICIENT_DATA':
            if checks or value['reason'] != 'source_unavailable_or_incompatible': raise ValueError()
        elif seen != RULES or value['reason'] != 'snapshot_checked' or value['status'] != ('FAIL' if any(c['violations'] for c in checks) else 'PASS'):
            raise ValueError()
        # Copy through JSON to ensure only aggregate primitives reach XCom.
        return json.loads(json.dumps(value))
    except (ValueError, TypeError, KeyError, OverflowError):
        raise AirflowException('Reconciliation result unavailable or invalid') from None


def execute_checks():
    return safe_result(reconcile().to_dict())


def validate_results(value):
    value = safe_result(value)
    if value['status'] == 'FAIL':
        raise AirflowFailException('Reconciliation integrity violations detected')
    if value['status'] == 'INSUFFICIENT_DATA':
        raise AirflowException('Reconciliation evidence insufficient')


def execution_summary(value):
    try:
        value = safe_result(value)
    except AirflowException:
        logging.getLogger(__name__).warning('Reconciliation summary: result unavailable')
        raise
    logging.getLogger(__name__).info('Reconciliation summary: %s', json.dumps(value,sort_keys=True))
    # An ALL_DONE leaf must not turn failed/upstream-failed work into DAG success.
    validate_results(value)
