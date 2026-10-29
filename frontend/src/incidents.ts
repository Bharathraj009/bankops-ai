import { parseSnapshot, ruleLabels, type Snapshot } from './monitoring'
const fail = (): never => {
  throw new Error('Invalid investigation evidence')
}
function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : fail()
}
function list(v: unknown, max: number): unknown[] {
  return Array.isArray(v) && v.length <= max ? v : fail()
}
function text(v: unknown): string {
  return typeof v === 'string' ? v : fail()
}
function choice<T extends string>(v: unknown, values: readonly T[]): T {
  return values.includes(v as T) ? (v as T) : fail()
}
function date(v: unknown): string {
  const s = text(v)
  return Number.isFinite(Date.parse(s)) ? s : fail()
}
function number(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : fail()
}
function count(v: unknown): number {
  const n = number(v)
  return Number.isSafeInteger(n) && n <= 100000 ? n : fail()
}
function bool(v: unknown): boolean {
  return typeof v === 'boolean' ? v : fail()
}
function identifier(v: unknown, length: number): string {
  const s = text(v)
  return new RegExp(`^[a-f0-9]{${length}}$`).test(s) && !/^0+$/.test(s)
    ? s
    : fail()
}
function correlation(v: unknown): string | null {
  if (v === null) return null
  const s = text(v)
  return /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(
    s,
  )
    ? s
    : fail()
}
export interface Detection extends Snapshot {
  detectedAt: string
  thresholds: {
    id: string
    observed: number | null
    threshold: number | null
    traffic: number | null
    minimum: number | null
  }[]
}
export function parseDetection(raw: unknown): Detection {
  const r = obj(raw),
    s = parseSnapshot(raw),
    rules = list(r.rules, 7),
    triggered = list(r.triggered_rules, 7).map(text)
  const actual = s.rules
    .filter((v) => v.state === 'incident')
    .map((v) => v.rule_id)
  if (
    new Set(triggered).size !== triggered.length ||
    triggered.some((id) => !actual.includes(id)) ||
    actual.some((id) => !triggered.includes(id)) ||
    (s.state === 'incident') !== actual.length > 0
  )
    fail()
  const optional = (v: unknown) =>
    v === null || v === undefined ? null : number(v)
  return {
    ...s,
    detectedAt: date(r.detected_at),
    thresholds: rules.map((raw) => {
      const v = obj(raw)
      return {
        id: text(v.rule_id),
        observed: optional(v.observed_value),
        threshold: optional(v.threshold),
        traffic: optional(v.observed_traffic),
        minimum: optional(v.minimum_traffic),
      }
    }),
  }
}
export const spanNames = [
  'http.request',
  'transfer.create',
  'transfer.read',
  'transfer.fund',
  'db.call',
  'other',
] as const
export interface Span {
  id: string
  name: string
  started: string
  duration: number
  failed: boolean
  slow: boolean
}
export interface Trace {
  id: string
  started: string
  duration: number
  failed: boolean
  truncated: boolean
  spans: Span[]
}
export interface LogEvent {
  time: string
  level: 'WARN' | 'ERROR'
  category: 'http_request_completed' | 'transfer_outcome'
  trace: string | null
  correlation: string | null
}
export const kinds = {
  http_error_degradation: 'HTTP error degradation',
  latency_degradation: 'Latency degradation',
  transfer_failure_degradation: 'Transfer failure degradation',
  service_unavailability: 'Service unavailability',
  database_call_degradation: 'Database call degradation',
} as const
export const uncertaintyLabels = {
  causality_unconfirmed: 'Causality is unconfirmed',
  bounded_sample: 'Evidence is a bounded sample',
  incomplete_evidence: 'Some evidence is incomplete',
  dependencies_not_observed: 'Dependencies were not observed',
} as const
export const stepLabels = {
  compare_metric_windows: 'Compare metric windows',
  inspect_safe_trace_timings: 'Inspect safe trace timings',
  check_dependency_health: 'Check dependency health',
  review_sanitized_error_events: 'Review sanitized error events',
  collect_additional_evidence: 'Collect additional evidence',
} as const
export const rcaReasons = {
  supported_hypotheses: 'Evidence-supported hypotheses returned',
  disabled: 'LLM inference is disabled on the backend',
  insufficient_evidence: 'Insufficient evidence for analysis',
  no_supported_hypotheses: 'No supported hypotheses',
  timeout: 'Provider timed out',
  unavailable: 'Provider unavailable',
  rate_limited: 'Provider rate limited',
  invalid_output: 'Provider output rejected by validation',
  input_limit: 'Evidence exceeded the analysis input limit',
} as const
type Kind = keyof typeof kinds
export interface RCA {
  status: 'hypotheses' | 'undetermined'
  reason: keyof typeof rcaReasons
  at: string
  hypotheses: { kind: Kind; confidence: 'low' | 'moderate'; refs: string[] }[]
  evidence: { id: string; source: string; at: string }[]
  uncertainty: (keyof typeof uncertaintyLabels)[]
  steps: (keyof typeof stepLabels)[]
}
export interface Report {
  started: string
  completed: string
  status: 'complete' | 'partial' | 'unavailable'
  detection: Detection
  traceStatus: string
  logStatus: string
  traces: Trace[]
  logs: LogEvent[]
  truncated: boolean
  facts: Record<string, number>
  correlations: {
    trace: string | null
    correlation: string | null
    present: boolean
    indexes: number[]
  }[]
  rca?: RCA
}
export function parseReport(raw: unknown, workflow = false): Report {
  const r = obj(raw),
    t = obj(r.traces),
    l = obj(r.logs)
  if (
    t.source !== 'jaeger' ||
    t.service !== 'banking-service' ||
    l.source !== 'local_jsonl' ||
    l.service !== 'banking-service'
  )
    fail()
  const traces = list(t.traces, 50).map((raw) => {
    const v = obj(raw)
    if (v.service !== 'banking-service') fail()
    return {
      id: identifier(v.trace_id, 32),
      started: date(v.started_at),
      duration: number(v.duration_seconds),
      failed: bool(v.failed),
      truncated: bool(v.truncated),
      spans: list(v.spans, 500).map((raw) => {
        const s = obj(raw)
        if (s.service !== 'banking-service') fail()
        return {
          id: identifier(s.span_id, 16),
          name: choice(s.name, spanNames),
          started: date(s.started_at),
          duration: number(s.duration_seconds),
          failed: bool(s.failed),
          slow: bool(s.slow),
        }
      }),
    }
  })
  if (traces.reduce((n, t) => n + t.spans.length, 0) > 2000) fail()
  const logs = list(l.events, 500).map((raw) => {
    const v = obj(raw)
    return {
      time: date(v.timestamp),
      level: choice(v.level, ['WARN', 'ERROR'] as const),
      category: choice(v.event_type, [
        'http_request_completed',
        'transfer_outcome',
      ] as const),
      trace: v.trace_id === null ? null : identifier(v.trace_id, 32),
      correlation: correlation(v.correlation_id),
    }
  })
  const f = obj(r.observed_facts),
    facts: Record<string, number> = {}
  for (const key of [
    'returned_trace_count',
    'failed_trace_count',
    'slow_span_count',
    'returned_log_event_count',
    'warn_event_count',
    'error_event_count',
  ])
    facts[key] = count(f[key])
  if (
    facts.returned_trace_count !== traces.length ||
    facts.returned_log_event_count !== logs.length ||
    facts.failed_trace_count !== traces.filter((v) => v.failed).length ||
    facts.warn_event_count !== logs.filter((v) => v.level === 'WARN').length ||
    facts.error_event_count !== logs.filter((v) => v.level === 'ERROR').length
  )
    fail()
  const correlations = list(r.correlations, 500).map((raw) => {
    const v = obj(raw),
      trace = v.trace_id === null ? null : identifier(v.trace_id, 32),
      c = correlation(v.correlation_id),
      indexes = list(v.log_event_indexes, 500).map(count)
    if (
      indexes.some(
        (i) => !logs[i] || logs[i].trace !== trace || logs[i].correlation !== c,
      ) ||
      bool(v.trace_present) !== traces.some((t) => t.id === trace)
    )
      fail()
    return {
      trace,
      correlation: c,
      present: v.trace_present as boolean,
      indexes,
    }
  })
  const report: Report = {
    started: date(r.started_at),
    completed: date(r.completed_at),
    status: choice(r.evidence_status, [
      'complete',
      'partial',
      'unavailable',
    ] as const),
    detection: parseDetection(r.detection),
    traceStatus: choice(t.status, [
      'ok',
      'missing',
      'partial',
      'timeout',
      'unavailable',
      'invalid_response',
    ] as const),
    logStatus: choice(l.status, [
      'ok',
      'missing',
      'not_configured',
      'unavailable',
      'partial',
    ] as const),
    traces,
    logs,
    truncated:
      bool(t.truncated) || bool(l.truncated) || traces.some((t) => t.truncated),
    facts,
    correlations,
  }
  if (Date.parse(report.completed) < Date.parse(report.started)) fail()
  if (workflow) report.rca = parseRCA(r.rca, report)
  return report
}
function parseRCA(raw: unknown, report: Report): RCA {
  const r = obj(raw)
  if (r.root_cause_confirmed !== false) fail()
  const evidence = list(r.evidence, 24).map((raw) => {
    const v = obj(raw),
      id = text(v.id),
      source = choice(v.source, ['rule', 'span', 'log'] as const),
      supports = list(v.supports, 5).map((k) =>
        choice(k, Object.keys(kinds) as Kind[]),
      )
    if (source === 'rule') {
      const rule = id.replace(/^rule\./, '')
      if (
        id !== `rule.${rule}` ||
        !Object.hasOwn(ruleLabels, rule) ||
        !report.detection.rules.some(
          (v) => v.rule_id === rule && v.state === 'incident',
        )
      )
        fail()
      const map: Record<string, Kind> = {
        high_http_error_rate: 'http_error_degradation',
        elevated_p95_latency: 'latency_degradation',
        high_transfer_failure_rate: 'transfer_failure_degradation',
        banking_unavailable: 'service_unavailability',
      }
      if (supports.length !== 1 || supports[0] !== map[rule]) fail()
      if (
        date(v.timestamp) !== report.detection.detectedAt ||
        v.observation !==
          (rule === 'banking_unavailable'
            ? 'service_down'
            : 'threshold_reached')
      )
        fail()
    }
    if (source === 'span') {
      const m = /^span\.(\d+)\.(\d+)$/.exec(id)
      const span = m
        ? report.traces[Number(m[1])]?.spans[Number(m[2])]
        : undefined
      if (
        !span ||
        span.name !== 'db.call' ||
        (!span.failed && !span.slow) ||
        supports.length !== 1 ||
        supports[0] !== 'database_call_degradation'
      )
        fail()
      if (
        !span ||
        date(v.timestamp) !== span.started ||
        v.observation !== 'slow_or_failed_db_call'
      )
        fail()
    }
    if (source === 'log') {
      const m = /^log\.(\d+)$/.exec(id)
      if (!m || !report.logs[Number(m[1])] || supports.length) fail()
      if (
        !m ||
        date(v.timestamp) !== report.logs[Number(m[1])].time ||
        v.observation !==
          (report.logs[Number(m[1])].level === 'ERROR'
            ? 'error_event'
            : 'warn_event')
      )
        fail()
    }
    return { id, source, at: date(v.timestamp), supports }
  })
  if (new Set(evidence.map((e) => e.id)).size !== evidence.length) fail()
  const hypotheses = list(r.hypotheses, 3).map((raw) => {
    const h = obj(raw),
      kind = choice(h.kind, Object.keys(kinds) as Kind[]),
      refs = list(h.supporting_evidence, 5).map(text)
    if (
      !refs.length ||
      new Set(refs).size !== refs.length ||
      refs.some(
        (id) => !evidence.some((e) => e.id === id && e.supports.includes(kind)),
      )
    )
      fail()
    return {
      kind,
      confidence: choice(h.confidence, ['low', 'moderate'] as const),
      refs,
    }
  })
  const status = choice(r.status, ['hypotheses', 'undetermined'] as const),
    reason = choice(
      r.reason,
      Object.keys(rcaReasons) as (keyof typeof rcaReasons)[],
    )
  if (
    (status === 'hypotheses') !== hypotheses.length > 0 ||
    (status === 'hypotheses') !== (reason === 'supported_hypotheses') ||
    new Set(hypotheses.map((h) => h.kind)).size !== hypotheses.length
  )
    fail()
  const uncertainty = list(r.uncertainty, 4).map((v) =>
      choice(
        v,
        Object.keys(uncertaintyLabels) as (keyof typeof uncertaintyLabels)[],
      ),
    ),
    steps = list(r.recommended_investigation_steps, 5).map((v) =>
      choice(v, Object.keys(stepLabels) as (keyof typeof stepLabels)[]),
    )
  if (
    !uncertainty.length ||
    !steps.length ||
    !uncertainty.includes('causality_unconfirmed')
  )
    fail()
  return {
    status,
    reason,
    at: date(r.analyzed_at),
    hypotheses,
    evidence,
    uncertainty,
    steps,
  }
}
export async function incidentRequest(
  action: 'detect' | 'investigate' | 'workflow',
  signal: AbortSignal,
): Promise<Detection | Report> {
  const path =
    action === 'workflow' ? 'workflows/investigate' : `incidents/${action}`
  const response = await fetch(`/investigation-api/${path}`, {
    method: action === 'workflow' ? 'POST' : 'GET',
    signal: AbortSignal.any([
      signal,
      AbortSignal.timeout(action === 'workflow' ? 70000 : 40000),
    ]),
    credentials: 'same-origin',
    cache: 'no-store',
    redirect: 'error',
  })
  if (!response.ok) throw new Error('Investigation service unavailable')
  const reader = response.body?.getReader()
  if (!reader) return fail()
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > 2097152) {
        await reader.cancel()
        fail()
      }
      chunks.push(value)
    }
  } finally {
    reader.releaseLock()
  }
  const joined = new Uint8Array(size)
  let offset = 0
  for (const c of chunks) {
    joined.set(c, offset)
    offset += c.length
  }
  const raw: unknown = JSON.parse(new TextDecoder().decode(joined))
  return action === 'detect'
    ? parseDetection(raw)
    : parseReport(raw, action === 'workflow')
}
