"""Bounded synthetic failure probe, never writes or contacts banking PostgreSQL."""
import json
import os
from datetime import UTC, datetime

from airflow.exceptions import AirflowException
from airflow.sdk.exceptions import AirflowFailException
from reconciliation import Check, Result, reconcile
from reconciliation import tasks

os.environ['BANKOPS_RECONCILIATION_DSN'] = 'host=127.0.0.1 port=1 dbname=unavailable connect_timeout=1'
try:
    tasks.validate_connectivity()
    raise AssertionError('Unavailable source accepted')
except AirflowException:
    pass
missing = reconcile().to_dict()
assert missing['status'] == 'INSUFFICIENT_DATA'
now = datetime.now(UTC).isoformat()
failed = Result(now,now,'FAIL','snapshot_checked',tuple(Check(rule,'FAIL' if i == 0 else 'PASS',1 if i == 0 else 0) for i,rule in enumerate(sorted(tasks.RULES)))).to_dict()
for function in (tasks.validate_results,tasks.execution_summary):
    try:
        function(failed)
        raise AssertionError('Violation accepted')
    except AirflowFailException:
        pass
    try:
        function(missing)
        raise AssertionError('Unavailable evidence accepted')
    except AirflowFailException:
        raise AssertionError('Insufficient evidence conflated with violation') from None
    except AirflowException:
        pass
print(json.dumps({'unavailable_connectivity_rejected':True,'insufficient_data_distinct':True,'violations_fail_without_retry':True,'banking_connection_used':False}))
