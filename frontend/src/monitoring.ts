export const definitions = {
  api_request_rate: {
    label: 'API request rate',
    unit: 'requests_per_second',
    suffix: 'req/s',
  },
  api_error_rate: { label: 'HTTP error ratio', unit: 'ratio', suffix: '%' },
  api_latency_p95: { label: 'API latency p95', unit: 'seconds', suffix: 'ms' },
  transfer_success_rate: {
    label: 'Transfer success rate',
    unit: 'requests_per_second',
    suffix: '/s',
  },
  transfer_failure_rate: {
    label: 'Transfer failure rate',
    unit: 'requests_per_second',
    suffix: '/s',
  },
  banking_availability: {
    label: 'Banking scrape availability',
    unit: 'ratio',
    suffix: '',
  },
  transfer_request_rate: {
    label: 'Transfer outcome rate',
    unit: 'requests_per_second',
    suffix: '/s',
  },
} as const
export type MetricName = keyof typeof definitions
export type State = 'Healthy' | 'Degraded' | 'Unavailable' | 'Insufficient data'
export interface Metric {
  name: MetricName
  status: string
  value: number | null
  sampled_at: string | null
}
export interface Snapshot {
  evidenceStatus: 'ok' | 'partial' | 'unavailable'
  evaluated_at: string
  collected_at: string
  state: 'healthy' | 'incident' | 'insufficient_data'
  metrics: Metric[]
  rules: { rule_id: string; state: string; reason: string }[]
}
export const ruleLabels: Record<string, string> = {
  banking_unavailable: 'Banking availability',
  high_http_error_rate: 'HTTP errors',
  elevated_p95_latency: 'API p95 latency',
  high_transfer_failure_rate: 'Transfer failures',
  reconciliation_financial_violations: 'Reconciliation violations',
  reconciliation_task_failure: 'Reconciliation tasks',
  reconciliation_insufficient_data: 'Reconciliation evidence',
}
export const reasons: Record<string, string> = {
  service_up: 'Scrape target is up',
  service_down: 'Scrape target is down',
  threshold_reached: 'Configured threshold reached',
  below_threshold: 'Below configured threshold',
  low_traffic: 'Traffic below evaluation minimum',
  missing_or_invalid_evidence: 'Evidence missing or invalid',
  reconciliation_failed: 'Reconciliation check failed',
  reconciliation_passed: 'Reconciliation check passed',
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Invalid monitoring response')
  return value as Record<string, unknown>
}
function timestamp(value: unknown): string {
  if (typeof value !== 'string' || !Number.isFinite(Date.parse(value)))
    throw new Error('Invalid timestamp')
  return value
}
export function parseSnapshot(raw: unknown): Snapshot {
  const r = object(raw),
    e = object(r.evidence)
  if (
    !['healthy', 'incident', 'insufficient_data'].includes(String(r.state)) ||
    e.source !== 'prometheus' ||
    e.service !== 'banking-service' ||
    e.window !== '5m' ||
    !['ok', 'partial', 'unavailable'].includes(String(e.status)) ||
    !Array.isArray(e.metrics) ||
    e.metrics.length !== 7 ||
    !Array.isArray(r.rules) ||
    r.rules.length < 4 ||
    r.rules.length > 7
  )
    throw new Error('Invalid monitoring evidence')
  const seen = new Set<string>()
  const metrics = e.metrics.map((rawMetric) => {
    const m = object(rawMetric),
      name = m.name as MetricName
    if (
      !Object.hasOwn(definitions, name) ||
      seen.has(name) ||
      m.unit !== definitions[name].unit ||
      ![
        'ok',
        'missing',
        'timeout',
        'unavailable',
        'query_error',
        'invalid_response',
      ].includes(String(m.status))
    )
      throw new Error('Invalid metric')
    seen.add(name)
    if (
      m.status === 'ok' &&
      (typeof m.value !== 'number' ||
        !Number.isFinite(m.value) ||
        m.value < 0 ||
        (name === 'api_error_rate' && m.value > 1) ||
        (name === 'banking_availability' && m.value !== 0 && m.value !== 1))
    )
      throw new Error('Invalid value')
    return {
      name,
      status: String(m.status),
      value: m.status === 'ok' ? (m.value as number) : null,
      sampled_at: m.status === 'ok' ? timestamp(m.sampled_at) : null,
    }
  })
  const rules = r.rules.map((rawRule) => {
    const v = object(rawRule)
    if (
      !Object.hasOwn(ruleLabels, String(v.rule_id)) ||
      !Object.hasOwn(reasons, String(v.reason)) ||
      !['healthy', 'incident', 'insufficient_data'].includes(String(v.state))
    )
      throw new Error('Invalid rule')
    return {
      rule_id: String(v.rule_id),
      state: String(v.state),
      reason: String(v.reason),
    }
  })
  if (
    new Set(rules.map((v) => v.rule_id)).size !== rules.length ||
    ![
      'banking_unavailable',
      'high_http_error_rate',
      'elevated_p95_latency',
      'high_transfer_failure_rate',
    ].every((id) => rules.some((v) => v.rule_id === id))
  )
    throw new Error('Missing rules')
  return {
    evidenceStatus: e.status as Snapshot['evidenceStatus'],
    state: r.state as Snapshot['state'],
    evaluated_at: timestamp(e.evaluated_at),
    collected_at: timestamp(e.collected_at),
    metrics,
    rules,
  }
}
export function fresh(time: string | null, now: number) {
  return (
    time !== null &&
    now - Date.parse(time) >= -1000 &&
    now - Date.parse(time) <= 60000
  )
}
export function observed(
  snapshot: Snapshot,
  name: MetricName,
  now: number,
): number | null {
  const m = snapshot.metrics.find((m) => m.name === name)
  return fresh(snapshot.evaluated_at, now) &&
    fresh(snapshot.collected_at, now) &&
    Date.parse(snapshot.collected_at) >= Date.parse(snapshot.evaluated_at) &&
    m?.status === 'ok' &&
    fresh(m.sampled_at, now)
    ? m.value
    : null
}
export function health(
  snapshot: Snapshot | undefined,
  now: number,
  failed: boolean,
): State {
  if (failed) return 'Unavailable'
  if (!snapshot || !fresh(snapshot.collected_at, now))
    return 'Insufficient data'
  if (
    snapshot.metrics.every((m) => m.status !== 'ok' && m.status !== 'missing')
  )
    return 'Unavailable'
  if (observed(snapshot, 'banking_availability', now) === 0)
    return 'Unavailable'
  if (!fresh(snapshot.evaluated_at, now)) return 'Insufficient data'
  const dependencies: Record<string, MetricName[]> = {
    banking_unavailable: ['banking_availability'],
    high_http_error_rate: ['api_error_rate', 'api_request_rate'],
    elevated_p95_latency: ['api_latency_p95', 'api_request_rate'],
    high_transfer_failure_rate: [
      'transfer_failure_rate',
      'transfer_request_rate',
    ],
  }
  if (
    snapshot.rules.some(
      (r) =>
        r.state === 'incident' &&
        (dependencies[r.rule_id] ?? []).every(
          (name) => observed(snapshot, name, now) !== null,
        ),
    )
  )
    return 'Degraded'
  if (
    snapshot.state === 'healthy' &&
    snapshot.evidenceStatus === 'ok' &&
    snapshot.rules.every((r) => r.state === 'healthy') &&
    snapshot.metrics.every((m) => observed(snapshot, m.name, now) !== null)
  )
    return 'Healthy'
  return 'Insufficient data'
}
export function formatMetric(name: MetricName, value: number | null) {
  if (value === null) return '—'
  if (name === 'banking_availability') return value === 1 ? 'Up' : 'Down'
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: name === 'api_latency_p95' ? 1 : 3,
  }).format(
    value *
      (name === 'api_error_rate' ? 100 : name === 'api_latency_p95' ? 1000 : 1),
  )
}
export async function monitoringGet(
  path: 'health' | 'incidents/detect',
  signal: AbortSignal,
) {
  const response = await fetch(`/monitoring-api/${path}`, {
    method: 'GET',
    signal,
    cache: 'no-store',
    credentials: 'same-origin',
    redirect: 'error',
  })
  if (!response.ok) throw new Error('Monitoring source unavailable')
  const body = await response.text()
  if (body.length > 65536) throw new Error('Oversized response')
  const data: unknown = JSON.parse(body)
  if (path === 'health') {
    const r = object(data)
    if (r.status !== 'ok' || r.service !== 'bankops-reliability-agent')
      throw new Error('Invalid health')
    return true
  }
  return parseSnapshot(data)
}
