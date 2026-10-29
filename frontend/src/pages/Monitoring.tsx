import { useEffect, useRef, useState } from 'react'
import { Activity, Clock3, RefreshCw, ShieldCheck } from 'lucide-react'
import { Badge } from '../components/ui'
import {
  definitions,
  formatMetric,
  fresh,
  health,
  monitoringGet,
  observed,
  reasons,
  ruleLabels,
  type MetricName,
  type Snapshot,
} from '../monitoring'

function Trend({
  samples,
  metric,
  range,
  now,
  gaps,
}: {
  samples: Snapshot[]
  metric: MetricName
  range: number
  now: number
  gaps: number[]
}) {
  const [focus, setFocus] = useState<number | null>(null)
  const points = samples.filter(
    (s) => Date.parse(s.evaluated_at) >= now - range * 60000,
  )
  const values = points.map((s) =>
    observed(s, metric, Date.parse(s.collected_at)),
  )
  const maximum = Math.max(
    0.001,
    ...values.filter((v): v is number => v !== null),
  )
  const xy = (i: number) =>
    `${40 + ((Date.parse(points[i].evaluated_at) - (now - range * 60000)) / (range * 60000)) * 520},${155 - ((values[i] ?? 0) / maximum) * 125}`
  const segments: string[][] = []
  values.forEach((v, i) => {
    if (
      i > 0 &&
      gaps.some(
        (time) =>
          time > Date.parse(points[i - 1].evaluated_at) &&
          time <= Date.parse(points[i].evaluated_at),
      )
    )
      segments.push([])
    if (v === null) {
      segments.push([])
      return
    }
    if (!segments.length) segments.push([])
    segments[segments.length - 1].push(xy(i))
  })
  const selected = focus === null ? undefined : points[focus]
  return (
    <div className="monitor-trend">
      <svg
        viewBox="0 0 600 190"
        role="group"
        aria-label={`${definitions[metric].label}, locally observed snapshots`}
      >
        <line x1="40" x2="560" y1="155" y2="155" className="chart-grid" />
        <line x1="40" x2="560" y1="90" y2="90" className="chart-grid" />
        <text x="5" y="32">
          {formatMetric(metric, maximum)}
        </text>
        <text x="15" y="158">
          0
        </text>
        {segments.map((segment, i) => (
          <polyline
            key={i}
            points={segment.join(' ')}
            fill="none"
            className="chart-line"
          />
        ))}
        {points.map((s, i) =>
          values[i] === null ? null : (
            <circle
              key={s.evaluated_at}
              cx={xy(i).split(',')[0]}
              cy={xy(i).split(',')[1]}
              r="5"
              tabIndex={0}
              role="button"
              aria-label={`${new Date(s.evaluated_at).toLocaleTimeString()}: ${formatMetric(metric, values[i])} ${definitions[metric].suffix}`}
              onFocus={() => setFocus(i)}
              onMouseEnter={() => setFocus(i)}
              onClick={() => setFocus(i)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') setFocus(i)
              }}
            >
              <title>
                {formatMetric(metric, values[i])} {definitions[metric].suffix}
              </title>
            </circle>
          ),
        )}
        <text x="40" y="182">
          {new Date(now - range * 60000).toLocaleTimeString()}
        </text>
        <text x="500" y="182">
          Now
        </text>
      </svg>
      <div
        className="chart-tooltip"
        role="status"
        aria-label="Observation details"
      >
        {selected
          ? `${new Date(selected.evaluated_at).toLocaleTimeString()} · ${formatMetric(metric, values[focus!])} ${definitions[metric].suffix}`
          : 'Focus or hover an observed point to inspect its value.'}
      </div>
      {!values.some((v) => v !== null) && (
        <p className="monitor-empty">
          No valid observations for this metric. Missing values are not plotted.
        </p>
      )}
      <p className="monitor-caption">
        {points.length} snapshots in this view. No backfill; gaps remain gaps.
        Each value uses the API’s fixed five-minute window.
      </p>
    </div>
  )
}
export default function Monitoring() {
  const [snapshot, setSnapshot] = useState<Snapshot>()
  const [samples, setSamples] = useState<Snapshot[]>([])
  const [gaps, setGaps] = useState<number[]>([])
  const [failed, setFailed] = useState(false)
  const [agent, setAgent] = useState<boolean | null>(null)
  const [agentAt, setAgentAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(30)
  const [range, setRange] = useState(15)
  const [metric, setMetric] = useState<MetricName>('api_request_rate')
  const [now, setNow] = useState(Date.now)
  const [tick, setTick] = useState(0)
  const running = useRef(false)
  useEffect(() => {
    const c = new AbortController()
    async function load() {
      if (running.current) return
      running.current = true
      setLoading(true)
      const startedAt = new Date().toISOString()
      const deadline = AbortSignal.any([c.signal, AbortSignal.timeout(12000)])
      try {
        const [d, h] = await Promise.allSettled([
          monitoringGet('incidents/detect', deadline),
          monitoringGet('health', deadline),
        ])
        if (c.signal.aborted) return
        setAgent(h.status === 'fulfilled' && h.value === true)
        setAgentAt(startedAt)
        if (d.status === 'fulfilled' && typeof d.value !== 'boolean') {
          const s = d.value
          setSnapshot(s)
          setSamples((old) =>
            [
              ...old.filter(
                (v) =>
                  v.evaluated_at !== s.evaluated_at &&
                  Date.parse(v.evaluated_at) > Date.now() - 3600000,
              ),
              s,
            ]
              .sort(
                (a, b) =>
                  Date.parse(a.evaluated_at) - Date.parse(b.evaluated_at),
              )
              .slice(-240),
          )
          setFailed(false)
        } else {
          setFailed(true)
          setGaps((old) =>
            [...old.filter((t) => t > Date.now() - 3600000), Date.now()].slice(
              -240,
            ),
          )
        }
      } finally {
        if (!disposed) running.current = false
        if (!c.signal.aborted) {
          setNow(Date.now())
          setLoading(false)
        } else if (!disposed) {
          setFailed(true)
          setAgent(false)
          setLoading(false)
        }
      }
    }
    let disposed = false
    void load()
    return () => {
      disposed = true
      c.abort()
      running.current = false
    }
  }, [tick])
  useEffect(() => {
    if (!refresh) return
    const id = setInterval(() => {
      if (!document.hidden && !running.current) setTick((t) => t + 1)
    }, refresh * 1000)
    return () => clearInterval(id)
  }, [refresh])
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5000)
    return () => clearInterval(id)
  }, [])
  const state = health(snapshot, now, failed)
  const stale = !!snapshot && (!fresh(snapshot.collected_at, now) || failed)
  const available = snapshot
    ? observed(snapshot, 'banking_availability', now)
    : null
  return (
    <div className="monitor-workspace">
      <section className="banking-banner">
        <div>
          <span className="eyebrow">LIVE OBSERVABILITY</span>
          <h2>A clear view of operational health.</h2>
          <p>Read-only evidence. Measured signals. No assumed health.</p>
        </div>
        <span
          className={`monitor-state state-${state.toLowerCase().replaceAll(' ', '-')}`}
        >
          {state}
        </span>
      </section>
      <p className="monitor-caption" role="status">
        {state === 'Healthy'
          ? 'All required observations and backend evaluations are fresh and healthy.'
          : state === 'Degraded'
            ? 'A backend rule is triggered. This is an observed evaluation, not a root-cause claim.'
            : state === 'Unavailable' && available === 0 && !failed
              ? 'Fresh scrape evidence reports the banking target down.'
              : state === 'Unavailable'
                ? 'Monitoring evidence is unavailable; banking health is not established.'
                : 'Required evidence is missing, stale, or below the minimum traffic for evaluation.'}
      </p>
      <div className="monitor-controls">
        <div>
          <Clock3 size={15} />
          <span>
            Last evidence:{' '}
            {snapshot
              ? new Date(snapshot.collected_at).toLocaleString()
              : 'Not yet received'}
          </span>
        </div>
        <label>
          Auto refresh
          <select
            aria-label="Auto refresh"
            value={refresh}
            onChange={(e) => setRefresh(Number(e.target.value))}
          >
            <option value={0}>Off</option>
            <option value={15}>15 seconds</option>
            <option value={30}>30 seconds</option>
            <option value={60}>60 seconds</option>
          </select>
        </label>
        <button
          className="button button-primary"
          disabled={loading}
          onClick={() => setTick((t) => t + 1)}
        >
          <RefreshCw size={15} />
          {loading ? 'Refreshing…' : 'Refresh now'}
        </button>
      </div>
      {failed && (
        <div className="bank-alert" role="alert">
          Monitoring evidence is unavailable. Banking health cannot be inferred
          from this connection failure.
        </div>
      )}
      {stale && (
        <div className="bank-alert" role="alert">
          Stale or cached evidence. Refresh successfully before relying on these
          observations.
        </div>
      )}
      {loading && !snapshot && (
        <div
          className="monitor-skeleton"
          role="status"
          aria-label="Loading monitoring evidence"
        >
          {[1, 2, 3].map((n) => (
            <div className="skeleton skeleton-card" key={n} />
          ))}
        </div>
      )}
      <section className="monitor-services bank-panel">
        <div>
          <ShieldCheck size={20} />
          <h2>Service signals</h2>
        </div>
        <div className="monitor-service">
          <strong>Banking service</strong>
          <Badge>
            {available === null
              ? 'Insufficient data'
              : available === 1
                ? 'Scrape target up'
                : 'Scrape target down'}
          </Badge>
          <small>
            Observed by Prometheus; not a transaction or readiness guarantee.
          </small>
        </div>
        <div className="monitor-service">
          <strong>Evidence agent</strong>
          <Badge>
            {agent === null
              ? 'Not observed'
              : !fresh(agentAt, now)
                ? 'Insufficient data'
                : agent
                  ? 'Process responding'
                  : 'Unavailable'}
          </Badge>
          <small>
            Agent process health only. It does not certify downstream systems.
          </small>
        </div>
      </section>
      <div className="monitor-kpis">
        {(
          [
            'api_request_rate',
            'api_error_rate',
            'api_latency_p95',
            'transfer_success_rate',
            'transfer_failure_rate',
            'transfer_request_rate',
          ] as MetricName[]
        ).map((name) => {
          const value = snapshot ? observed(snapshot, name, now) : null
          const m = snapshot?.metrics.find((m) => m.name === name)
          return (
            <section
              aria-label={definitions[name].label}
              className="bank-panel monitor-kpi"
              key={name}
            >
              <div>
                <span>{definitions[name].label}</span>
                <Activity size={16} />
              </div>
              <strong>
                {formatMetric(name, value)}{' '}
                <small>{value === null ? '' : definitions[name].suffix}</small>
              </strong>
              <p>
                {value === null
                  ? m?.status === 'ok'
                    ? 'Stale or invalid observation'
                    : (m?.status.replaceAll('_', ' ') ?? 'Awaiting evidence')
                  : 'Observed · 5-minute window'}
              </p>
              <small>
                {m?.sampled_at
                  ? `Sample ${new Date(m.sampled_at).toLocaleTimeString()}`
                  : 'No valid sample timestamp'}
              </small>
              {failed && <small>Cached observation</small>}
            </section>
          )
        })}
      </div>
      <section className="bank-panel">
        <div className="section-heading">
          <div>
            <h2>Signal history</h2>
            <p>
              Snapshots observed in this open workspace, not historical
              Prometheus queries.
            </p>
          </div>
        </div>
        <div className="bank-toolbar">
          <label>
            Signal
            <select
              aria-label="Signal"
              value={metric}
              onChange={(e) => setMetric(e.target.value as MetricName)}
            >
              {Object.entries(definitions)
                .filter(([name]) => name !== 'banking_availability')
                .map(([name, d]) => (
                  <option key={name} value={name}>
                    {d.label}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Local observation range
            <select
              aria-label="Local observation range"
              value={range}
              onChange={(e) => setRange(Number(e.target.value))}
            >
              <option value={15}>Last 15 minutes</option>
              <option value={30}>Last 30 minutes</option>
              <option value={60}>Last 60 minutes</option>
            </select>
          </label>
        </div>
        <Trend
          key={`${metric}-${range}`}
          samples={samples}
          metric={metric}
          range={range}
          now={now}
          gaps={gaps}
        />
      </section>
      <section className="bank-panel">
        <h2>Evaluation context</h2>
        <p>
          Backend-configured thresholds and minimum traffic requirements govern
          these evaluations. Low traffic and missing evidence never mean
          healthy.
        </p>
        <div className="monitor-rules">
          {snapshot?.rules.map((r) => (
            <div key={r.rule_id}>
              <strong>{ruleLabels[r.rule_id]}</strong>
              <Badge>
                {stale
                  ? 'Stale evaluation'
                  : r.state === 'incident'
                    ? 'Triggered'
                    : r.state === 'healthy'
                      ? 'Within rule'
                      : 'Insufficient data'}
              </Badge>
              <small>{reasons[r.reason]}</small>
            </div>
          )) ?? <p>No rule evaluations received.</p>}
        </div>
        <p className="monitor-caption">
          Transfer failures measure HTTP outcomes, not persisted FAILED transfer
          records. Retries and development funding are excluded by the
          collector.
        </p>
      </section>
      <details className="bank-panel">
        <summary>Recent observation values</summary>
        <div className="bank-table-wrap">
          <table>
            <caption>
              Latest 20 locally collected snapshots ·{' '}
              {definitions[metric].label}
            </caption>
            <thead>
              <tr>
                <th>Evaluation time</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {samples
                .slice(-20)
                .reverse()
                .map((s) => (
                  <tr key={s.evaluated_at}>
                    <td>{new Date(s.evaluated_at).toLocaleString()}</td>
                    <td>
                      {formatMetric(
                        metric,
                        observed(s, metric, Date.parse(s.collected_at)),
                      )}{' '}
                      {definitions[metric].suffix}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          {!samples.length && <p>No observations collected.</p>}
        </div>
      </details>
    </div>
  )
}
