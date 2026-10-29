export function airflowFixture() {
  const tasks = [
    'validate_read_only_connectivity',
    'execute_reconciliation',
    'validate_results',
    'execution_summary',
  ]
  const checks = [
    'completed_double_entry',
    'account_balances',
    'ledger_consistency',
    'lifecycle_ledger',
  ]
  return {
    airflow: {
      source: 'airflow',
      dag: 'bankops_daily_reconciliation',
      collected_at: new Date().toISOString(),
      status: 'ok',
      truncated: false,
      runs: [
        {
          observed_at: new Date(Date.now() - 3600000).toISOString(),
          state: 'success',
          outcome: 'pass',
          summary_status: 'PASS',
          tasks: tasks.map((task) => ({ task, state: 'success' })),
          checks: checks.map((rule) => ({ rule, violations: 0 })),
        },
      ],
    },
  }
}
