import { useEffect, useRef, useState } from 'react'
import { CalendarClock, Database, RefreshCw, ShieldCheck } from 'lucide-react'
import { Badge, Dialog, PageSkeleton } from '../components/ui'
import {
  assessment,
  checkLabels,
  current,
  loadAirflow,
  outcomeLabels,
  taskLabels,
  type Airflow,
  type Run,
} from '../reconciliation'

const time = (v: string) =>
  new Date(v).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  })
function Result({ value }: { value: string }) {
  const tone =
    value === 'PASS' || value === 'success'
      ? 'success'
      : [
            'FAIL',
            'failed',
            'upstream_failed',
            'Financial violations',
            'Task failure',
          ].includes(value)
        ? 'danger'
        : ['running', 'In progress'].includes(value)
          ? 'blue'
          : 'warning'
  return <Badge tone={tone}>{value}</Badge>
}
export default function Reconciliation() {
  const [evidence, setEvidence] = useState<Airflow | null>(null)
  const [loading, setLoading] = useState(true),
    [failed, setFailed] = useState(false)
  const [now, setNow] = useState(Date.now),
    [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState<Run | null>(null)
  const [revision, setRevision] = useState(0)
  const lock = useRef(false)
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 5000)
    return () => clearInterval(interval)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    const timer = setTimeout(() => controller.abort(), 15000)
    lock.current = true
    loadAirflow(controller.signal)
      .then((a) => {
        if (disposed) return
        setEvidence(a)
        setFailed(false)
        setNow(Date.now())
      })
      .catch(() => {
        if (!disposed) setFailed(true)
      })
      .finally(() => {
        clearTimeout(timer)
        if (!disposed) {
          lock.current = false
          setLoading(false)
        }
      })
    return () => {
      disposed = true
      clearTimeout(timer)
      controller.abort()
    }
  }, [revision])
  const stale = !!evidence && !current(evidence, now)
  const result = assessment(evidence, now, failed)
  const runs = evidence?.runs ?? []
  const shown = runs.filter((r) => filter === 'all' || r.outcome === filter)
  const lastPass = runs.find((r) => r.outcome === 'pass')
  return (
    <div className="banking-workspace reconciliation-workspace">
      <section className="banking-banner recon-banner">
        <div>
          <span className="eyebrow">FINANCIAL ASSURANCE / READ ONLY</span>
          <h2>Reconciliation, with evidence.</h2>
          <p>
            Deterministic checks. Clear operational context. No financial
            writes.
          </p>
        </div>
        <ShieldCheck size={40} aria-hidden="true" />
      </section>
      <div className="recon-toolbar">
        <div>
          <h2>Daily reconciliation</h2>
          <p>Banking ledger integrity · bounded backend sample</p>
        </div>
        <button
          className="button button-secondary"
          disabled={loading}
          onClick={() => {
            if (lock.current) return
            lock.current = true
            setLoading(true)
            setRevision((v) => v + 1)
          }}
        >
          <RefreshCw size={16} className={loading ? 'recon-refreshing' : ''} />{' '}
          {loading ? 'Refreshing…' : 'Refresh evidence'}
        </button>
      </div>
      <div aria-live="polite" className="recon-notices">
        {failed && (
          <p role="alert">
            Evidence request failed. Retained records are historical; current
            reconciliation is unavailable.
          </p>
        )}
        {stale && (
          <p role="status">
            Stale evidence — refresh required. Recorded results do not establish
            current integrity.
          </p>
        )}
        {!loading &&
          !failed &&
          (!evidence || evidence.status === 'disabled') && (
            <p>
              Airflow evidence is not configured. No reconciliation result is
              available.
            </p>
          )}
        {evidence &&
          evidence.status !== 'ok' &&
          evidence.status !== 'disabled' && (
            <p>
              Collection status: {evidence.status.replaceAll('_', ' ')}.
              Evidence is incomplete; no overall PASS.
            </p>
          )}
        {evidence?.truncated && (
          <p>The backend sample is truncated. Additional runs may exist.</p>
        )}
      </div>
      {loading && !evidence ? (
        <PageSkeleton />
      ) : (
        <>
          <section className="recon-kpis" aria-label="Reconciliation overview">
            <article className="bank-panel">
              <Database size={19} />
              <span>Sample assessment</span>
              <Result value={result} />
              <small>
                Historical checks, never an incident-resolution claim.
              </small>
            </article>
            <article className="bank-panel">
              <ShieldCheck size={19} />
              <span>Airflow read access</span>
              <strong>
                {failed
                  ? 'Unavailable'
                  : stale
                    ? 'Stale'
                    : !evidence || evidence.status === 'disabled'
                      ? 'Not configured'
                      : evidence.status === 'ok'
                        ? 'Responding'
                        : evidence.status.replaceAll('_', ' ')}
              </strong>
              <small>Evidence API reachability, not scheduler health.</small>
            </article>
            <article className="bank-panel">
              <CalendarClock size={19} />
              <span>Last successful run in sample</span>
              <strong>
                {lastPass ? time(lastPass.observed_at) : 'Not observed'}
              </strong>
              <small>
                {lastPass
                  ? 'Recorded PASS; not a current balance guarantee.'
                  : 'Missing evidence is never PASS.'}
              </small>
            </article>
          </section>
          <section
            className="bank-panel recon-runs"
            aria-labelledby="runs-title"
          >
            <div className="recon-toolbar">
              <div>
                <span className="eyebrow">RUN REGISTER</span>
                <h2 id="runs-title">Observed DAG runs</h2>
              </div>
              <label className="recon-filter">
                Result filter
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="all">All results</option>
                  {Object.entries(outcomeLabels).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="recon-caption">
              {evidence
                ? `Collected ${time(evidence.collected_at)}`
                : 'No collection timestamp'}{' '}
              · Newest observed first · {shown.length} of {runs.length} returned
              runs
            </p>
            {shown.length ? (
              <div className="bank-table-wrap">
                <table>
                  <caption className="sr-only">
                    Read-only reconciliation run sample
                  </caption>
                  <thead>
                    <tr>
                      <th>Run observation</th>
                      <th>DAG state</th>
                      <th>Reconciliation evidence</th>
                      <th>Review</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((r, i) => (
                      <tr key={`${r.observed_at}-${i}`}>
                        <td>
                          <time dateTime={r.observed_at}>
                            {time(r.observed_at)}
                          </time>
                          <small>Observed run · no stable ID supplied</small>
                        </td>
                        <td>
                          <Result value={r.state} />
                        </td>
                        <td>
                          <Result value={outcomeLabels[r.outcome]} />
                          {r.summary_status && (
                            <small>Recorded summary: {r.summary_status}</small>
                          )}
                        </td>
                        <td>
                          <button
                            className="button button-secondary"
                            aria-label={`Review run ${time(r.observed_at)}`}
                            onClick={() => setSelected(r)}
                          >
                            View details
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="recon-empty">
                <Database size={28} />
                <h3>
                  {runs.length
                    ? 'No runs match this filter'
                    : 'No run evidence available'}
                </h3>
                <p>
                  {runs.length
                    ? 'Choose another result to review the returned sample.'
                    : 'Missing or unavailable runs cannot establish financial integrity.'}
                </p>
                {filter !== 'all' && (
                  <button
                    className="button button-secondary"
                    onClick={() => setFilter('all')}
                  >
                    Clear filter
                  </button>
                )}
              </div>
            )}
          </section>
          <aside className="recon-boundary">
            <ShieldCheck size={18} />
            <p>
              Financial violations are checker-reported findings. Airflow task
              failures indicate execution problems and do not establish
              financial corruption. Run start/end times and execution durations
              are not supplied by this privacy-safe API.
            </p>
          </aside>
        </>
      )}
      <Dialog
        open={selected !== null}
        onClose={() => setSelected(null)}
        title="Reconciliation run details"
        className="recon-dialog"
      >
        {selected && (
          <>
            <p>
              Observed{' '}
              <time dateTime={selected.observed_at}>
                {time(selected.observed_at)}
              </time>
            </p>
            <Result value={outcomeLabels[selected.outcome]} />
            <p>
              Recorded summary: {selected.summary_status ?? 'Not available'}.
              This snapshot does not claim an incident is resolved.
            </p>
            {(stale || failed) && (
              <p role="status">
                This evidence is stale or unavailable. Refresh before relying on
                it.
              </p>
            )}
            <h3>Task progression</h3>
            <ol className="recon-tasks">
              {Object.entries(taskLabels).map(([task, label]) => (
                <li key={task}>
                  <span>{label}</span>
                  <Result
                    value={
                      selected.tasks.find((t) => t.task === task)?.state ??
                      'Not observed'
                    }
                  />
                </li>
              ))}
            </ol>
            <h3>Financial checks</h3>
            {selected.checks.length ? (
              <ul className="recon-checks">
                {selected.checks.map((c) => (
                  <li key={c.rule}>
                    <span>{checkLabels[c.rule]}</span>
                    <strong>{c.violations} violations</strong>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No validated financial check summary was returned.</p>
            )}
            <small>
              Counts may overlap across rules. No account or transaction details
              are exposed. Execution duration unavailable.
            </small>
          </>
        )}
      </Dialog>
    </div>
  )
}
