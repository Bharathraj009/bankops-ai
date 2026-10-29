from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from airflow.exceptions import AirflowException
from airflow.sdk.exceptions import AirflowFailException
from airflow.dag_processing.dagbag import DagBag
import pytest

from reconciliation import Check, Result
from reconciliation import tasks


def report(status='PASS'):
    checks = tuple(Check(rule,'FAIL' if status == 'FAIL' and i == 0 else 'PASS',1 if status == 'FAIL' and i == 0 else 0) for i,rule in enumerate(sorted(tasks.RULES)))
    return Result('2026-10-15T00:00:00+00:00','2026-10-15T00:01:00+00:00',status,
        'source_unavailable_or_incompatible' if status == 'INSUFFICIENT_DATA' else 'snapshot_checked',
        () if status == 'INSUFFICIENT_DATA' else checks).to_dict()


def test_dag_import_configuration_and_topology(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('Parse-time connection')
    monkeypatch.setattr(tasks.psycopg,'connect',forbidden)
    monkeypatch.setattr(tasks,'reconcile',forbidden)
    folder = Path(__file__).resolve().parents[1] / 'dags'
    bag = DagBag(dag_folder=str(folder),safe_mode=False)
    assert not bag.import_errors
    dag = bag.dags['bankops_daily_reconciliation']
    assert dag.catchup is False and dag.max_active_runs == 1
    assert dag.schedule == '0 0 * * *'
    assert str(dag.timezone) == 'UTC'
    assert set(dag.task_ids) == {'validate_read_only_connectivity','execute_reconciliation','validate_results','execution_summary'}
    for task in dag.tasks:
        assert task.retries == 2 and task.retry_delay == timedelta(minutes=5)
        assert task.show_return_value_in_logs is False
    assert dag.get_task('validate_read_only_connectivity').downstream_task_ids == {'execute_reconciliation'}
    assert dag.get_task('execute_reconciliation').downstream_task_ids == {'validate_results','execution_summary'}
    # Validation remains a leaf: ALL_DONE summary can never mask its failure.
    assert {task.task_id for task in dag.leaves} == {'validate_results','execution_summary'}
    assert dag.get_task('execution_summary').trigger_rule == 'all_done'
    assert dag.get_task('validate_results').trigger_rule == 'all_success'
    assert [task.task_id for task in dag.tasks if task.do_xcom_push] == ['execute_reconciliation']
    called = []
    monkeypatch.setattr(tasks,'validate_connectivity',lambda:called.append('connectivity'))
    monkeypatch.setattr(tasks,'execute_checks',lambda:report())
    dag.get_task('validate_read_only_connectivity').python_callable()
    value = dag.get_task('execute_reconciliation').python_callable()
    dag.get_task('validate_results').python_callable(value)
    summary = dag.get_task('execution_summary').python_callable
    class TaskInstance:
        def xcom_pull(self,**kwargs):
            assert kwargs == {'task_ids':'execute_reconciliation','key':'return_value'}
            return value
    monkeypatch.setitem(summary.__globals__,'get_current_context',lambda:{'ti':TaskInstance()})
    summary()
    assert called == ['connectivity']


@pytest.mark.parametrize('status',['PASS','FAIL','INSUFFICIENT_DATA'])
def test_execute_bounded_aggregate(monkeypatch,status):
    value = report(status)
    monkeypatch.setattr(tasks,'reconcile',lambda: SimpleNamespace(to_dict=lambda:value))
    result = tasks.execute_checks()
    import json
    assert len(json.dumps(result)) < 2000
    assert result['status'] == status


@pytest.mark.parametrize('function',[tasks.validate_results,tasks.execution_summary])
def test_pass_fail_and_insufficient_distinct(function,caplog):
    function(report())
    with pytest.raises(AirflowFailException,match='integrity violations'):
        function(report('FAIL'))
    with pytest.raises(AirflowException,match='evidence insufficient') as error:
        function(report('INSUFFICIENT_DATA'))
    assert type(error.value) is AirflowException  # Eligible for configured retries.
    assert 'PRIVATE' not in caplog.text


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(account_id='PRIVATE'),
    lambda r:r.update(status='PRIVATE'),
    lambda r:r.update(reason='PRIVATE'),
    lambda r:r.update(checks=[]),
    lambda r:r.update(started_at='PRIVATE'),
    lambda r:r['checks'][0].update(rule='PRIVATE'),
    lambda r:r['checks'][0].update(violations=-1),
    lambda r:r['checks'][0].update(status='FAIL'),
    lambda r:r.update(completed_at='2025-01-01T00:00:00Z'),
])
def test_invalid_or_sensitive_xcom_never_logged(mutation,caplog):
    value = deepcopy(report())
    mutation(value)
    with pytest.raises(AirflowException) as error: tasks.execution_summary(value)
    assert 'PRIVATE' not in str(error.value) + caplog.text


def test_missing_result_not_pass(caplog):
    with pytest.raises(AirflowException): tasks.execution_summary(None)
    assert 'result unavailable' in caplog.text


def test_connectivity_missing_failure_and_readonly(monkeypatch):
    monkeypatch.delenv('BANKOPS_RECONCILIATION_DSN',raising=False)
    with pytest.raises(AirflowException): tasks.validate_connectivity()
    monkeypatch.setenv('BANKOPS_RECONCILIATION_DSN','PRIVATE')
    def failure(*args,**kwargs): raise tasks.psycopg.OperationalError('PRIVATE')
    monkeypatch.setattr(tasks.psycopg,'connect',failure)
    with pytest.raises(AirflowException) as error: tasks.validate_connectivity()
    assert 'PRIVATE' not in str(error.value)
    class Connection:
        rolled_back = False
        queries = []
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,query): self.queries.append(query); return self
        def fetchone(self): return ('on',)
        def rollback(self): self.rolled_back = True
    connection = Connection()
    def connect(dsn,**kwargs):
        assert dsn == 'PRIVATE'
        assert 'default_transaction_read_only=on' in kwargs['options']
        return connection
    monkeypatch.setattr(tasks.psycopg,'connect',connect)
    tasks.validate_connectivity()
    assert connection.rolled_back
    assert connection.queries == ['SET TRANSACTION READ ONLY','SHOW transaction_read_only','SELECT 1']
