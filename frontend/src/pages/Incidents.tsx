import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowUpRight,
  Bot,
  FileSearch,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import { Badge, Dialog } from '../components/ui'
import {
  definitions,
  formatMetric,
  fresh,
  health,
  observed,
  reasons,
  ruleLabels,
} from '../monitoring'
import {
  incidentRequest,
  kinds,
  rcaReasons,
  stepLabels,
  uncertaintyLabels,
  type Detection,
  type Report,
} from '../incidents'

const facts: Record<string, string> = {
  returned_trace_count: 'Returned traces',
  failed_trace_count: 'Failed traces',
  slow_span_count: 'Slow spans',
  returned_log_event_count: 'Sanitized log events',
  warn_event_count: 'WARN events',
  error_event_count: 'ERROR events',
}
function statusLabel(status: string) {
  return (
    (
      {
        ok: 'Available',
        missing: 'No observations',
        not_configured: 'Not configured',
        partial: 'Partial',
        complete: 'Complete',
        unavailable: 'Unavailable',
        timeout: 'Timed out',
        invalid_response: 'Invalid response',
      } as Record<string, string>
    )[status] ?? 'Unknown'
  )
}
export function EvidenceReport({ report }: { report: Report }) {
  const [logLimit, setLogLimit] = useState(50)
  const rca = report.rca
  return (
    <div className="incident-report">
      <section className="bank-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">OBSERVED FACTS</span>
            <h2>Investigation evidence</h2>
            <p>
              Captured {new Date(report.completed).toLocaleString()}. This
              report is a snapshot, not a resolution claim.
            </p>
          </div>
          <Badge>{statusLabel(report.status)} evidence</Badge>
        </div>
        <div className="incident-facts">
          {Object.entries(report.facts).map(([key, value]) => (
            <div key={key}>
              <span>{facts[key]}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
        <ol className="incident-timeline">
          <li>
            <span>Investigation started</span>
            <time>{new Date(report.started).toLocaleString()}</time>
          </li>
          <li>
            <span>Detection evaluated</span>
            <time>
              {new Date(report.detection.detectedAt).toLocaleString()}
            </time>
          </li>
          <li>
            <span>Report assembled</span>
            <time>{new Date(report.completed).toLocaleString()}</time>
          </li>
          {rca && (
            <li>
              <span>RCA result returned · {rca.status}</span>
              <time>{new Date(rca.at).toLocaleString()}</time>
            </li>
          )}
        </ol>
        {report.truncated && (
          <p className="bank-alert">
            Evidence is truncated by source limits. This is not a complete
            operational history.
          </p>
        )}
      </section>
      <section className="bank-panel">
        <h2>Metric evidence</h2>
        <p>
          Values as observed at report collection · fixed five-minute rate
          window.
        </p>
        <div className="incident-facts">
          {report.detection.metrics.map((m) => (
            <div key={m.name}>
              <span>{definitions[m.name].label}</span>
              <strong>
                {formatMetric(
                  m.name,
                  observed(
                    report.detection,
                    m.name,
                    Date.parse(report.detection.collected_at),
                  ),
                )}{' '}
                <small>
                  {m.name === 'banking_availability'
                    ? ''
                    : definitions[m.name].suffix}
                </small>
              </strong>
              <small>
                {m.status === 'ok'
                  ? 'Observed sample'
                  : m.status.replaceAll('_', ' ')}
              </small>
            </div>
          ))}
        </div>
      </section>
      <section className="bank-panel">
        <div className="section-heading">
          <h2>Trace evidence</h2>
          <Badge>{statusLabel(report.traceStatus)}</Badge>
        </div>
        <p>
          Bounded trace/span categories only; no request paths or attributes are
          displayed.
        </p>
        {!report.traces.length && (
          <div className="bank-empty">
            No traces returned. Missing traces do not demonstrate health.
          </div>
        )}
        {report.traces.slice(0, 20).map((t, i) => (
          <details className="incident-trace" key={t.id}>
            <summary>
              Trace {i + 1} · {t.duration.toFixed(3)} s ·{' '}
              {t.failed ? 'Error observed' : 'No error flag in sample'}
            </summary>
            <p className="bank-id">Trace ID: {t.id}</p>
            <p>
              {new Date(t.started).toLocaleString()}
              {t.truncated ? ' · Truncated' : ''}
            </p>
            <div className="bank-table-wrap">
              <table>
                <caption>Returned spans, first 20 of {t.spans.length}</caption>
                <thead>
                  <tr>
                    <th>Span category</th>
                    <th>Duration</th>
                    <th>Indicators</th>
                  </tr>
                </thead>
                <tbody>
                  {t.spans.slice(0, 20).map((s) => (
                    <tr key={s.id}>
                      <td>{s.name}</td>
                      <td>{s.duration.toFixed(3)} s</td>
                      <td>
                        {s.failed
                          ? 'Error observed'
                          : s.slow
                            ? 'Slow span'
                            : 'No error/slow flag'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ))}
        {report.traces.length > 20 && (
          <p>
            Showing 20 of {report.traces.length} returned traces to keep this
            view bounded.
          </p>
        )}
      </section>
      <section className="bank-panel">
        <div className="section-heading">
          <h2>Sanitized log evidence</h2>
          <Badge>{statusLabel(report.logStatus)}</Badge>
        </div>
        <p>
          Only category, level, timestamp and validated correlation identifiers.
          Raw messages, stack traces and prompts are never shown.
        </p>
        {!report.logs.length ? (
          <div className="bank-empty">
            No log events returned. The source may be idle, unavailable or
            unconfigured.
          </div>
        ) : (
          <ol className="incident-timeline">
            {report.logs.slice(0, logLimit).map((l, i) => (
              <li id={`log-event-${i}`} key={i}>
                <Badge>{l.level}</Badge>
                <strong>
                  {l.category === 'transfer_outcome'
                    ? 'Transfer outcome'
                    : 'HTTP request completed'}
                </strong>
                <time>{new Date(l.time).toLocaleString()}</time>
                {l.trace && <small className="bank-id">Trace: {l.trace}</small>}
                {l.correlation && (
                  <small className="bank-id">
                    Correlation: {l.correlation}
                  </small>
                )}
              </li>
            ))}
          </ol>
        )}
        {report.logs.length > logLimit && (
          <button className="button" onClick={() => setLogLimit((n) => n + 50)}>
            Show 50 more log events
          </button>
        )}
      </section>
      <section className="bank-panel">
        <h2>Exact-ID correlations</h2>
        <p>
          Matching identifiers establish identity, not causality. No
          timestamp-based guesses are added.
        </p>
        {!report.correlations.length ? (
          <p>No exact-ID correlations returned.</p>
        ) : (
          report.correlations.slice(0, 20).map((c, i) => (
            <div className="incident-correlation" key={i}>
              <strong>
                {c.present
                  ? 'Returned trace matched'
                  : 'Trace not present in returned sample'}
              </strong>
              <small className="bank-id">
                {c.trace ?? 'No trace ID'} ·{' '}
                {c.correlation ?? 'No correlation ID'}
              </small>
              <span>Matched log event indexes: {c.indexes.join(', ')}</span>
            </div>
          ))
        )}
        {report.correlations.length > 20 && (
          <p>
            Showing first 20 of {report.correlations.length} correlation groups.
          </p>
        )}
      </section>
      <section className="bank-panel incident-hypotheses">
        <span className="eyebrow">HYPOTHESES · NOT CONFIRMED ROOT CAUSES</span>
        <h2>AI analysis</h2>
        {!rca ? (
          <p>
            Not requested. Observed evidence above contains no AI-generated
            explanation.
          </p>
        ) : (
          <>
            <Badge>
              {rca.status === 'hypotheses'
                ? 'Supported hypotheses'
                : 'Undetermined'}
            </Badge>
            <p>{rcaReasons[rca.reason]}. No root cause is confirmed.</p>
            <section aria-label="Retrieved evidence references">
              <h3>Retrieved evidence references</h3>
              <p>Synthetic troubleshooting context, not proof of causality.</p>
              {rca.sources.length === 0 && <p>No retrieved documents.</p>}
              {rca.sources.map((source) => (
                <details key={source.id}>
                  <summary>{source.title}</summary>
                  <p className="bank-id">{source.id}</p>
                  <p>{source.reference}</p>
                  <p>{source.content}</p>
                </details>
              ))}
            </section>
            {rca.hypotheses.map((h) => (
              <article className="hypothesis-card" key={h.kind}>
                <h3>{kinds[h.kind]}</h3>
                <Badge>Reported confidence: {h.confidence}</Badge>
                <p>Supporting evidence references:</p>
                {h.documents.length > 0 && (
                  <p>Retrieved citations: {h.documents.join(', ')}</p>
                )}
                <ul>
                  {h.refs.map((id) => (
                    <li key={id}>
                      {id} · {rca.evidence.find((e) => e.id === id)?.source} ·{' '}
                      {new Date(
                        rca.evidence.find((e) => e.id === id)!.at,
                      ).toLocaleString()}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
            <h3>Uncertainty</h3>
            <ul>
              {rca.uncertainty.map((u) => (
                <li key={u}>{uncertaintyLabels[u]}</li>
              ))}
            </ul>
            <h3>Recommended investigation steps</h3>
            <ul>
              {rca.steps.map((s) => (
                <li key={s}>{stepLabels[s]}</li>
              ))}
            </ul>
            <p>
              These are suggestions only. No approval, remediation or banking
              write is initiated.
            </p>
          </>
        )}
      </section>
    </div>
  )
}

export default function Incidents({
  active,
  investigation,
}: {
  active: boolean
  investigation: boolean
}) {
  const location = useLocation()
  const navigate = useNavigate()
  const [detection, setDetection] = useState<Detection>()
  const [report, setReport] = useState<Report>()
  const [filter, setFilter] = useState('incident')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [failure, setFailure] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [now, setNow] = useState(Date.now)
  const running = useRef(false),
    action = useRef<AbortController | null>(null),
    detecting = useRef<AbortController | null>(null)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5000)
    return () => {
      clearInterval(timer)
      action.current?.abort()
    }
  }, [])
  useEffect(() => {
    if (!active || running.current) return
    const c = new AbortController()
    let disposed = false
    detecting.current = c
    async function detect() {
      running.current = true
      setBusy('detect')
      setError('')
      try {
        const result = await incidentRequest('detect', c.signal)
        if (!disposed) setDetection(result as Detection)
      } catch {
        if (!disposed) {
          setFailure('detect')
          setError(
            'Detection service unavailable or response invalid. Current incident state is unknown.',
          )
        }
      } finally {
        if (!disposed) {
          detecting.current = null
          running.current = false
          setBusy('')
          setNow(Date.now())
        }
      }
    }
    void detect()
    return () => {
      disposed = true
      c.abort()
      if (detecting.current === c) {
        detecting.current = null
        running.current = false
      }
    }
  }, [active, refresh])
  async function collect(workflow: boolean) {
    if (running.current) return
    running.current = true
    setBusy(workflow ? 'workflow' : 'evidence')
    setError('')
    const c = new AbortController()
    action.current = c
    try {
      const result = (await incidentRequest(
        workflow ? 'workflow' : 'investigate',
        c.signal,
      )) as Report
      setReport(result)
      setDetection(result.detection)
      setConfirm(false)
    } catch {
      if (!c.signal.aborted) {
        setFailure(workflow ? 'workflow' : 'evidence')
        setError(
          workflow
            ? 'AI investigation failed or its response was rejected. No automatic retry was made; backend inference may already have run.'
            : 'Evidence investigation failed or its response was rejected. Previously captured evidence is retained as a historical snapshot.',
        )
      }
    } finally {
      running.current = false
      setBusy('')
      setNow(Date.now())
    }
  }
  const stale =
    !!detection &&
    (!fresh(detection.detectedAt, now) || !fresh(detection.collected_at, now))
  const state =
    error && failure === 'detect'
      ? 'Unavailable'
      : stale
        ? 'Insufficient data'
        : health(detection, now, false)
  const selectedId = new URLSearchParams(location.search).get('rule') || ''
  const rules =
    detection?.rules.filter(
      (r) =>
        (filter === 'all' || r.state === filter) &&
        ruleLabels[r.rule_id].toLowerCase().includes(query.toLowerCase()),
    ) ?? []
  const detail = detection?.rules.find((r) => r.rule_id === selectedId)
  const meta = detection?.thresholds.find((r) => r.id === selectedId)
  return (
    <div className="incident-workspace">
      <section className="banking-banner">
        <div>
          <span className="eyebrow">
            {investigation
              ? 'EVIDENCE-LED INVESTIGATION'
              : 'INCIDENT OPERATIONS'}
          </span>
          <h2>
            {investigation
              ? 'Build understanding. Preserve uncertainty.'
              : 'Signals that deserve attention.'}
          </h2>
          <p>Current rule evaluations, not a fabricated incident history.</p>
        </div>
        <FileSearch size={32} />
      </section>
      <div className="monitor-controls">
        <div>
          Last detection:{' '}
          {detection
            ? new Date(detection.detectedAt).toLocaleString()
            : 'Not received'}
        </div>
        <button
          className="button"
          disabled={!!busy}
          onClick={() => setRefresh((n) => n + 1)}
        >
          <RefreshCw size={15} /> Refresh detection
        </button>
        <button
          className="button"
          disabled={!!busy}
          onClick={() => void collect(false)}
        >
          <ShieldCheck size={15} /> Collect evidence
        </button>
        <button
          className="button button-primary"
          disabled={!!busy}
          onClick={() => setConfirm(true)}
        >
          <Bot size={16} /> Run AI RCA
        </button>
      </div>
      {busy && (
        <div className="bank-loading skeleton" role="status">
          {busy === 'workflow'
            ? 'Running LangGraph investigation. Analysis is optional on the backend; no automatic retries.'
            : busy === 'detect'
              ? 'Loading current detection…'
              : 'Collecting metrics, traces and sanitized logs…'}
        </div>
      )}
      {error && (
        <div className="bank-alert" role="alert">
          {error}
        </div>
      )}
      {stale && (
        <div className="bank-alert" role="alert">
          Detection is stale. Refresh before treating these evaluations as
          current.
        </div>
      )}
      <section className="bank-panel">
        <div className="section-heading">
          <div>
            <h2>Detection overview</h2>
            <p>
              {!detection
                ? 'No detection snapshot received.'
                : state === 'Healthy'
                  ? 'No incidents detected in this fresh snapshot.'
                  : state === 'Degraded'
                    ? 'Triggered rules require investigation. No root cause is established.'
                    : state === 'Unavailable'
                      ? 'Service or evidence unavailable. Review observed evidence.'
                      : 'Insufficient evidence to establish that there are no incidents.'}
            </p>
          </div>
          <Badge>{stale ? 'Stale snapshot' : state}</Badge>
        </div>
        <div className="incident-facts">
          <div>
            <span>Triggered rules in snapshot</span>
            <strong>
              {detection
                ? detection.rules.filter((r) => r.state === 'incident').length
                : '—'}
            </strong>
          </div>
          <div>
            <span>Metric evidence</span>
            <strong>
              {detection
                ? statusLabel(detection.evidenceStatus)
                : 'Not received'}
            </strong>
          </div>
          <div>
            <span>Severity</span>
            <strong className="incident-no-severity">
              Not provided by API
            </strong>
          </div>
        </div>
        <p className="monitor-caption">
          Rule IDs identify evaluations, not durable incident records. No
          severity scores or inferred incident IDs are assigned.
        </p>
      </section>
      <section className="bank-panel">
        <div className="section-heading">
          <h2>Rule evaluations</h2>
          <Link
            className="button"
            to={investigation ? '/incidents' : '/investigation'}
          >
            {investigation
              ? 'Open incident workspace'
              : 'Open AI investigation'}{' '}
            <ArrowUpRight size={15} />
          </Link>
        </div>
        <div className="bank-toolbar">
          <label>
            Evaluation filter
            <select
              aria-label="Evaluation filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="incident">Triggered rules</option>
              <option value="all">All evaluations</option>
              <option value="insufficient_data">Insufficient evidence</option>
              <option value="healthy">Within rule</option>
            </select>
          </label>
          <label>
            Search rules
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Rule name"
            />
          </label>
        </div>
        {!rules.length ? (
          <div className="bank-empty">
            {detection
              ? 'No rule evaluations match this filter. Check the overall evidence state above.'
              : 'Awaiting real detection evidence.'}
          </div>
        ) : (
          <div className="incident-rule-list">
            {rules.map((r) => (
              <button
                className={`incident-rule ${selectedId === r.rule_id ? 'selected' : ''}`}
                key={r.rule_id}
                onClick={() =>
                  navigate(`${location.pathname}?rule=${r.rule_id}`)
                }
              >
                <strong>{ruleLabels[r.rule_id]}</strong>
                <Badge>
                  {r.state === 'incident'
                    ? 'Triggered'
                    : r.state === 'healthy'
                      ? 'Within rule'
                      : 'Insufficient evidence'}
                </Badge>
                <span>{reasons[r.reason]}</span>
              </button>
            ))}
          </div>
        )}
      </section>
      {detail && (
        <section className="bank-panel">
          <h2>{ruleLabels[detail.rule_id]} · observed details</h2>
          <p>{reasons[detail.reason]}. Severity is not supplied by this API.</p>
          <div className="incident-facts">
            {[
              ['Observed value', meta?.observed],
              ['Configured threshold', meta?.threshold],
              ['Observed traffic /s', meta?.traffic],
              ['Minimum traffic /s', meta?.minimum],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <span>{label}</span>
                <strong>{value ?? 'Not provided'}</strong>
              </div>
            ))}
          </div>
          <p>
            Values retain backend units: error rules use ratios, latency uses
            seconds, transfer failures use outcomes/second. Missing evidence is
            never zero.
          </p>
          <Link className="button" to={`/investigation?rule=${detail.rule_id}`}>
            Investigate this rule <ArrowUpRight size={15} />
          </Link>
        </section>
      )}
      {report ? (
        <EvidenceReport key={report.completed} report={report} />
      ) : (
        <section className="bank-panel bank-empty">
          <FileSearch size={30} />
          <h2>No investigation report captured</h2>
          <p>
            Collect read-only evidence, or explicitly run the LangGraph workflow
            with optional backend-configured AI analysis.
          </p>
        </section>
      )}
      <Dialog
        open={confirm && active}
        dismissible={busy !== 'workflow'}
        onClose={() => setConfirm(false)}
        title="Run AI root cause analysis"
      >
        <div className="bank-form">
          <p>
            This explicitly starts the existing LangGraph workflow: detection,
            sanitized evidence collection, report assembly and optional RCA.
          </p>
          <p>
            If a provider is enabled on the backend, this may make an inference
            request. The browser cannot enable inference or change provider
            configuration. Hypotheses are never confirmed causes.
          </p>
          <p>
            No financial writes, approval proposals or remediation actions will
            be executed. No automatic retries.
          </p>
          {error && <p role="alert">{error}</p>}
          <button
            className="button button-primary"
            disabled={!!busy}
            onClick={() => void collect(true)}
          >
            {busy === 'workflow'
              ? 'Investigating…'
              : 'Confirm AI investigation'}
          </button>
        </div>
      </Dialog>
    </div>
  )
}
