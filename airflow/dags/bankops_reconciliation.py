"""Daily aggregate reconciliation. No connections or environment reads at parse time."""
from datetime import datetime, timedelta, timezone

from airflow.sdk import dag, task, get_current_context
from reconciliation import tasks


@dag(dag_id='bankops_daily_reconciliation', schedule='0 0 * * *',
     start_date=datetime(2026,1,1,tzinfo=timezone.utc), catchup=False,
     max_active_runs=1, default_args={'retries':2,'retry_delay':timedelta(minutes=5)},
     tags=['bankops','reconciliation'])
def banking_reconciliation():
    @task(task_id='validate_read_only_connectivity', do_xcom_push=False, show_return_value_in_logs=False)
    def connectivity():
        tasks.validate_connectivity()

    @task(task_id='execute_reconciliation', show_return_value_in_logs=False)
    def execute():
        return tasks.execute_checks()

    @task(task_id='validate_results', do_xcom_push=False, show_return_value_in_logs=False)
    def validate(value):
        tasks.validate_results(value)

    @task(task_id='execution_summary', trigger_rule='all_done', do_xcom_push=False, show_return_value_in_logs=False)
    def summary():
        value = get_current_context()['ti'].xcom_pull(task_ids='execute_reconciliation', key='return_value')
        tasks.execution_summary(value)

    checked = connectivity()
    result = execute()
    validate(result)
    summarized = summary()
    checked >> result
    result >> summarized


dag = banking_reconciliation()
