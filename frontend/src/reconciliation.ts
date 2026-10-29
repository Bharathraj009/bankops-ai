// Project only bounded, allowlisted evidence. Never render upstream messages or IDs.
export const taskLabels = {
  validate_read_only_connectivity: 'Read-only connectivity',
  execute_reconciliation: 'Execute reconciliation',
  validate_results: 'Validate results',
  execution_summary: 'Privacy-safe summary',
} as const
export const checkLabels = {
  completed_double_entry: 'Completed transfer double entry',
  account_balances: 'Ledger-derived account balances',
  ledger_consistency: 'Ledger consistency',
  lifecycle_ledger: 'Transfer lifecycle and ledger',
} as const
export const outcomeLabels = {
  pass: 'PASS',
  financial_violations: 'Financial violations',
  task_failure: 'Task failure',
  insufficient_data: 'INSUFFICIENT_DATA',
  in_progress: 'In progress',
} as const
type Task = keyof typeof taskLabels
type Check = keyof typeof checkLabels
type Outcome = keyof typeof outcomeLabels
export type Run = {
  observed_at: string
  state: string
  outcome: Outcome
  summary_status: 'PASS' | 'FAIL' | 'INSUFFICIENT_DATA' | null
  checks: { rule: Check; violations: number }[]
  tasks: { task: Task; state: string | null }[]
}
export type Airflow = {
  collected_at: string
  status: string
  truncated: boolean
  runs: Run[]
}
const states = [
  'success',
  'failed',
  'upstream_failed',
  'queued',
  'running',
  'scheduled',
  'up_for_retry',
  'skipped',
  'deferred',
  'removed',
  'restarting',
]
function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v))
    throw Error('Invalid evidence')
  return v as Record<string, unknown>
}
function date(v: unknown): string {
  if (
    typeof v !== 'string' ||
    v.length > 40 ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(
      v,
    ) ||
    !Number.isFinite(Date.parse(v))
  )
    throw Error('Invalid evidence')
  return v
}
function member<T extends string>(v: unknown, keys: readonly T[]): T {
  if (typeof v !== 'string' || !keys.includes(v as T))
    throw Error('Invalid evidence')
  return v as T
}
export function parseAirflow(payload: unknown): Airflow | null {
  const raw = object(payload).airflow
  if (raw === null || raw === undefined) return null
  const a = object(raw)
  if (
    a.source !== 'airflow' ||
    a.dag !== 'bankops_daily_reconciliation' ||
    typeof a.truncated !== 'boolean' ||
    !Array.isArray(a.runs) ||
    a.runs.length > 10
  )
    throw Error('Invalid evidence')
  const collected_at = date(a.collected_at)
  const runs = a.runs
    .map((value): Run => {
      const r = object(value),
        observed_at = date(r.observed_at)
      if (
        Date.parse(observed_at) > Date.parse(collected_at) ||
        !Array.isArray(r.tasks) ||
        r.tasks.length > 4 ||
        !Array.isArray(r.checks) ||
        r.checks.length > 4
      )
        throw Error('Invalid evidence')
      const tasks = r.tasks.map((v) => {
        const t = object(v)
        return {
          task: member(t.task, Object.keys(taskLabels) as Task[]),
          state: t.state === null ? null : member(t.state, states),
        }
      })
      const checks = r.checks.map((v) => {
        const c = object(v)
        if (
          !Number.isInteger(c.violations) ||
          (c.violations as number) < 0 ||
          (c.violations as number) > 1000000
        )
          throw Error('Invalid evidence')
        return {
          rule: member(c.rule, Object.keys(checkLabels) as Check[]),
          violations: c.violations as number,
        }
      })
      if (
        new Set(tasks.map((t) => t.task)).size !== tasks.length ||
        new Set(checks.map((c) => c.rule)).size !== checks.length
      )
        throw Error('Invalid evidence')
      const state = member(r.state, ['success', 'failed', 'queued', 'running'])
      const outcome = member(r.outcome, Object.keys(outcomeLabels) as Outcome[])
      const summary_status =
        r.summary_status === null
          ? null
          : member(r.summary_status, [
              'PASS',
              'FAIL',
              'INSUFFICIENT_DATA',
            ] as const)
      if (
        (summary_status === 'PASS' || summary_status === 'FAIL') &&
        (checks.length !== 4 ||
          checks.some((c) => c.violations > 0) !== (summary_status === 'FAIL'))
      )
        throw Error('Invalid evidence')
      if (
        (summary_status === null || summary_status === 'INSUFFICIENT_DATA') &&
        checks.length
      )
        throw Error('Invalid evidence')
      if (
        outcome === 'pass' &&
        (state !== 'success' ||
          summary_status !== 'PASS' ||
          tasks.length !== 4 ||
          tasks.some((t) => t.state !== 'success'))
      )
        throw Error('Invalid evidence')
      if (
        outcome === 'financial_violations' &&
        (state !== 'failed' || summary_status !== 'FAIL')
      )
        throw Error('Invalid evidence')
      if (outcome === 'task_failure' && state !== 'failed')
        throw Error('Invalid evidence')
      if (outcome === 'in_progress' && !['running', 'queued'].includes(state))
        throw Error('Invalid evidence')
      return { observed_at, state, outcome, summary_status, checks, tasks }
    })
    .sort((a, b) => Date.parse(b.observed_at) - Date.parse(a.observed_at))
  return {
    collected_at,
    status: member(a.status, [
      'disabled',
      'ok',
      'partial',
      'missing',
      'unavailable',
      'timeout',
      'invalid_response',
    ]),
    truncated: a.truncated,
    runs,
  }
}
export function current(a: Airflow | null, now: number) {
  return (
    !!a &&
    now - Date.parse(a.collected_at) >= -5000 &&
    now - Date.parse(a.collected_at) <= 60000
  )
}
export function assessment(a: Airflow | null, now: number, failed = false) {
  if (failed) return 'Unavailable'
  if (
    !a ||
    !current(a, now) ||
    a.status !== 'ok' ||
    a.truncated ||
    !a.runs.length
  )
    return 'INSUFFICIENT_DATA'
  if (a.runs.some((r) => r.outcome === 'financial_violations')) return 'FAIL'
  if (a.runs.some((r) => r.outcome === 'task_failure')) return 'Task failure'
  return a.runs.every((r) => r.outcome === 'pass')
    ? 'PASS'
    : 'INSUFFICIENT_DATA'
}
export async function loadAirflow(signal: AbortSignal) {
  const response = await fetch('/reconciliation-api/incidents/detect', {
    method: 'GET',
    signal,
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
  })
  if (!response.ok) throw Error('Evidence unavailable')
  // Bound the response before JSON parsing, including chunked responses.
  const reader = response.body?.getReader()
  if (!reader) throw Error('Evidence unavailable')
  const chunks: Uint8Array[] = []
  let length = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      length += value.length
      if (length > 524288) throw Error('Evidence too large')
      chunks.push(value)
    }
  } finally {
    await reader.cancel()
  }
  const data = new Uint8Array(length)
  let offset = 0
  for (const chunk of chunks) {
    data.set(chunk, offset)
    offset += chunk.length
  }
  return parseAirflow(JSON.parse(new TextDecoder().decode(data)))
}
