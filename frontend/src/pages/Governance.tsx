import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ClipboardCheck,
  KeyRound,
  LogOut,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import { Badge, Dialog } from '../components/ui'
import { uuid } from '../banking'
import { ruleLabels } from '../monitoring'
import {
  actions,
  decisionReasons,
  GovernanceError,
  governanceRequest,
  outcomes,
  safeActions,
  verificationReasons,
  type Proposal,
  type Execution,
  type Verification,
  type Operation,
} from '../governance'
type Resource<T> = {
  state: 'not_loaded' | 'missing' | 'unavailable' | 'loaded'
  value?: T
}
export default function Governance({
  active,
  remediation,
}: {
  active: boolean
  remediation: boolean
}) {
  const [role, setRole] = useState<'proposer' | 'reviewer'>('reviewer'),
    [draft, setDraft] = useState(''),
    [connected, setConnected] = useState(false)
  const secret = useRef(''),
    running = useRef(false),
    controller = useRef<AbortController | null>(null),
    generation = useRef(0)
  const [lookup, setLookup] = useState(''),
    [proposal, setProposal] = useState<Proposal>(),
    [execution, setExecution] = useState<Resource<Execution>>({
      state: 'not_loaded',
    }),
    [verification, setVerification] = useState<Resource<Verification>>({
      state: 'not_loaded',
    })
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [locked, setLocked] = useState(false),
    [confirmation, setConfirmation] = useState<Operation | null>(null),
    [reason, setReason] =
      useState<keyof typeof decisionReasons>('reviewed_evidence'),
    [updated, setUpdated] = useState<string>()
  function disconnect() {
    generation.current++
    controller.current?.abort()
    secret.current = ''
    setDraft('')
    setConnected(false)
    setProposal(undefined)
    setExecution({ state: 'not_loaded' })
    setVerification({ state: 'not_loaded' })
    setUpdated(undefined)
    setConfirmation(null)
    setNotice('')
    setError('')
    setLocked(false)
    running.current = false
    setBusy(false)
  }
  useEffect(
    () => () => {
      secret.current = ''
      controller.current?.abort()
    },
    [],
  )
  useEffect(() => {
    if (!locked) return
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [locked])
  function fail(e: unknown) {
    if (
      e instanceof GovernanceError &&
      (e.status === 401 || e.status === 403)
    ) {
      disconnect()
      setError(e.message)
      return
    }
    setError(
      e instanceof GovernanceError
        ? e.message
        : 'Service unavailable or response invalid. The operation may already have committed; read the latest records. No automatic retry was made.',
    )
  }
  function connect() {
    if (!/^[\x21-\x7E]{32,256}$/.test(draft)) {
      setError(
        'Use a valid 32–256 character bearer credential without whitespace.',
      )
      return
    }
    secret.current = draft
    setDraft('')
    setConnected(true)
    setError('')
    setNotice(
      'Credential held in memory only. Role selection is not server attestation; the backend authorizes every request.',
    )
  }
  async function load() {
    if (running.current || !connected) return
    if (!uuid.test(lookup)) {
      setError('Enter a valid proposal UUID.')
      return
    }
    running.current = true
    setBusy(true)
    setError('')
    const epoch = generation.current,
      c = new AbortController()
    controller.current = c
    try {
      const p = (await governanceRequest(
        'proposal',
        lookup,
        secret.current,
        c.signal,
      )) as Proposal
      if (epoch !== generation.current) return
      setProposal(p)
      setExecution({ state: 'not_loaded' })
      setVerification({ state: 'not_loaded' })
      const results = await Promise.allSettled([
        governanceRequest('execution', p.id, secret.current, c.signal),
        governanceRequest('verification', p.id, secret.current, c.signal),
      ])
      if (epoch !== generation.current) return
      for (const r of results)
        if (
          r.status === 'rejected' &&
          r.reason instanceof GovernanceError &&
          [401, 403].includes(r.reason.status)
        )
          throw r.reason
      function resource<T>(r: PromiseSettledResult<unknown>): Resource<T> {
        return r.status === 'fulfilled'
          ? { state: 'loaded', value: r.value as T }
          : r.reason instanceof GovernanceError && r.reason.status === 404
            ? { state: 'missing' }
            : { state: 'unavailable' }
      }
      const e = resource<Execution>(results[0]),
        v = resource<Verification>(results[1])
      if (e.value && e.value.action !== p.action)
        throw new Error('Binding mismatch')
      setExecution(e)
      setVerification(v)
      setLocked(e.state === 'unavailable' || v.state === 'unavailable')
      setUpdated(new Date().toISOString())
      setNotice(
        'Latest authorized records loaded. These snapshots do not establish incident resolution.',
      )
    } catch (e) {
      if (epoch === generation.current) {
        setProposal(undefined)
        setExecution({ state: 'not_loaded' })
        setVerification({ state: 'not_loaded' })
        setLocked(true)
        fail(e)
      }
    } finally {
      if (epoch === generation.current) {
        running.current = false
        setBusy(false)
      }
    }
  }
  async function submit() {
    if (
      running.current ||
      !confirmation ||
      !proposal ||
      role !== 'reviewer' ||
      !connected ||
      locked
    )
      return
    const operation = confirmation
    running.current = true
    setBusy(true)
    setError('')
    setLocked(true)
    const epoch = generation.current,
      c = new AbortController()
    controller.current = c
    try {
      const body =
        operation === 'approve' || operation === 'reject'
          ? { reason }
          : operation === 'execute'
            ? {
                action: proposal.action,
                parameters: { service: 'banking-service' },
              }
            : { basis: 'recorded_execution' }
      const result = await governanceRequest(
        operation,
        proposal.id,
        secret.current,
        c.signal,
        body,
      )
      if (epoch !== generation.current) return
      if (operation === 'approve' || operation === 'reject')
        setProposal(result as Proposal)
      if (operation === 'execute') {
        const e = result as Execution
        if (e.action !== proposal.action) throw new Error('Binding mismatch')
        setExecution({ state: 'loaded', value: e })
      }
      if (operation === 'verify')
        setVerification({ state: 'loaded', value: result as Verification })
      setConfirmation(null)
      setNotice(
        'Backend returned the recorded result. Refresh records before any further state-changing action. No incident resolution is determined.',
      )
      setUpdated(new Date().toISOString())
    } catch (e) {
      if (epoch === generation.current) {
        setConfirmation(null)
        fail(e)
      }
    } finally {
      if (epoch === generation.current) {
        running.current = false
        setBusy(false)
      }
    }
  }
  const executable =
    !!proposal && safeActions.some((a) => a === proposal.action)
  const canDecide =
    connected &&
    role === 'reviewer' &&
    proposal?.status === 'PENDING' &&
    execution.state === 'missing' &&
    verification.state === 'missing' &&
    !locked &&
    !busy
  const canExecute =
    connected &&
    role === 'reviewer' &&
    proposal?.status === 'APPROVED' &&
    executable &&
    execution.state === 'missing' &&
    verification.state === 'missing' &&
    !locked &&
    !busy
  const canVerify =
    connected &&
    role === 'reviewer' &&
    proposal?.status === 'APPROVED' &&
    execution.state === 'loaded' &&
    verification.state === 'missing' &&
    !locked &&
    !busy
  return (
    <div className="governance-workspace">
      <section className="banking-banner">
        <div>
          <span className="eyebrow">HUMAN OVERSIGHT</span>
          <h2>
            {remediation
              ? 'Approved intent. Bounded execution.'
              : 'Review evidence. Record a deliberate decision.'}
          </h2>
          <p>
            Explicit authorization at every stage. No automatic execution or
            retries.
          </p>
        </div>
        <ClipboardCheck size={32} />
      </section>
      {error && (
        <div className="bank-alert" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <p role="status" className="bank-notice">
          {notice}
        </p>
      )}
      <section className="bank-panel">
        <div className="section-heading">
          <h2>Authorized session</h2>
          <Badge>
            {connected ? `${role} workspace` : 'No credential loaded'}
          </Badge>
        </div>
        {!connected ? (
          <form
            className="bank-form"
            onSubmit={(e) => {
              e.preventDefault()
              connect()
            }}
          >
            <p>
              Use one role credential at a time. Selecting a role does not grant
              permissions. The backend determines the actual role from the
              credential.
            </p>
            <label>
              Workspace role
              <select
                aria-label="Workspace role"
                value={role}
                onChange={(e) => {
                  setRole(e.target.value as typeof role)
                  setDraft('')
                }}
              >
                <option value="reviewer">Human reviewer</option>
                <option value="proposer">Proposer · read-only workspace</option>
              </select>
            </label>
            <label>
              Bearer credential
              <input
                autoComplete="off"
                type="password"
                name="governance-credential"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                required
                minLength={32}
                maxLength={256}
              />
            </label>
            <button className="button button-primary">
              <KeyRound size={15} /> Use credential
            </button>
            <p>
              No credential is persisted, included in URLs, logged or sent to
              AI. This UI does not enable backend features.
            </p>
          </form>
        ) : (
          <>
            <p>
              The selected role is {role}; backend authorization remains
              authoritative. Logical actors are not personal identities.
            </p>
            <button className="button" disabled={busy} onClick={disconnect}>
              <LogOut size={15} /> Clear credential and records
            </button>
          </>
        )}
      </section>
      <section className="bank-panel">
        <div className="section-heading">
          <div>
            <h2>Retrieve proposal</h2>
            <p>
              No global listing API exists. Load a real proposal by ID from your
              trusted proposer.
            </p>
          </div>
          <Link
            className="button"
            to={remediation ? '/approvals' : '/remediation'}
          >
            {remediation ? 'Open approvals' : 'Open remediation'}
          </Link>
        </div>
        <form
          className="bank-toolbar"
          onSubmit={(e) => {
            e.preventDefault()
            void load()
          }}
        >
          <label>
            Proposal ID
            <input
              value={lookup}
              disabled={busy}
              onChange={(e) => setLookup(e.target.value.trim())}
              required
              placeholder="Proposal UUID"
            />
          </label>
          <button
            className="button button-primary"
            disabled={!connected || busy}
          >
            <RefreshCw size={15} />{' '}
            {busy ? 'Request in progress…' : 'Load / refresh records'}
          </button>
        </form>
        <p className="monitor-caption">
          Last loaded/result:{' '}
          {updated ? new Date(updated).toLocaleString() : 'Not received'}. No
          background polling. Refresh also reads execution and verification
          records independently.
        </p>
        {locked && (
          <p className="bank-alert">
            State-changing controls are locked. Explicitly read the latest
            records before proceeding; an earlier operation may already have
            committed.
          </p>
        )}
      </section>
      {!proposal ? (
        <section className="bank-panel bank-empty">
          <ShieldCheck size={30} />
          <h2>No authorized proposal loaded</h2>
          <p>
            Unavailable or unauthorized records are never replaced with demo
            proposals.
          </p>
        </section>
      ) : (
        <>
          <section className="bank-panel">
            <div className="section-heading">
              <div>
                <span className="eyebrow">PROPOSED INTENT</span>
                <h2>{actions[proposal.action]}</h2>
              </div>
              <Badge>{proposal.status}</Badge>
            </div>
            <dl className="bank-details">
              <div>
                <dt>Proposal ID</dt>
                <dd>{proposal.id}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>
                  {new Date(proposal.created).toLocaleString()} ·
                  proposal_service
                </dd>
              </div>
              <div>
                <dt>Fixed execution target</dt>
                <dd>
                  {executable
                    ? 'service = banking-service'
                    : 'Intent only. This legacy action is not executable.'}
                </dd>
              </div>
              {proposal.decided && (
                <div>
                  <dt>Decision recorded</dt>
                  <dd>
                    {new Date(proposal.decided).toLocaleString()} ·
                    human_reviewer ·{' '}
                    {proposal.reason && decisionReasons[proposal.reason]}
                  </dd>
                </div>
              )}
            </dl>
            <h3>Proposer-supplied evidence references</h3>
            <p>
              References are assertions, not persisted proof of an incident or
              RCA. Current investigation evidence must be reviewed separately.
            </p>
            <ul>
              {proposal.refs.map((ref, i) => (
                <li key={`${ref}-${i}`}>
                  <Link to={`/investigation?rule=${ref.slice(5)}`}>
                    {ruleLabels[ref.slice(5)]} · {ref}
                  </Link>
                </li>
              ))}
            </ul>
            {role === 'proposer' ? (
              <p className="bank-alert">
                Proposer credentials cannot approve, reject, execute or verify.
                A separately held human reviewer credential is required.
              </p>
            ) : (
              <>
                <label className="governance-reason">
                  Decision reason
                  <select
                    aria-label="Decision reason"
                    value={reason}
                    disabled={!canDecide}
                    onChange={(e) => setReason(e.target.value as typeof reason)}
                  >
                    {Object.entries(decisionReasons).map(([key, label]) => (
                      <option value={key} key={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="bank-toolbar">
                  <button
                    className="button button-primary"
                    disabled={!canDecide}
                    onClick={() => setConfirmation('approve')}
                  >
                    Approve proposal
                  </button>
                  <button
                    className="button"
                    disabled={!canDecide}
                    onClick={() => setConfirmation('reject')}
                  >
                    Reject proposal
                  </button>
                </div>
                <p>
                  Both decisions are terminal. Approval records intent and does
                  not execute anything.
                </p>
              </>
            )}
          </section>
          <section className="bank-panel">
            <div className="section-heading">
              <h2>Execution record</h2>
              <Badge>
                {execution.value?.status ??
                  (execution.state === 'missing'
                    ? 'No recorded execution'
                    : execution.state === 'unavailable'
                      ? 'Unavailable'
                      : 'Not loaded')}
              </Badge>
            </div>
            {execution.value ? (
              <>
                <p>
                  Started {new Date(execution.value.started).toLocaleString()}
                </p>
                <p>
                  {execution.value.completed
                    ? `Completed ${new Date(execution.value.completed).toLocaleString()}`
                    : 'RUNNING may persist after interruption. There is no automatic retry or claim reset.'}
                </p>
                <p>
                  {execution.value.outcome
                    ? outcomes[execution.value.outcome]
                    : 'No terminal outcome recorded.'}
                </p>
              </>
            ) : (
              <p>
                {execution.state === 'unavailable'
                  ? 'Execution lookup failed. Absence cannot be inferred.'
                  : 'Only an APPROVED proposal for one of the two fixed read-only actions can execute.'}
              </p>
            )}
            <button
              className="button button-primary"
              disabled={!canExecute}
              onClick={() => setConfirmation('execute')}
            >
              Execute approved read-only action
            </button>
            <p>
              Backend execution remains disabled by default. No restart,
              scaling, shell command, arbitrary URL or financial write is
              supported.
            </p>
          </section>
          <section className="bank-panel">
            <div className="section-heading">
              <h2>Post-execution verification</h2>
              <Badge>
                {verification.value?.status ??
                  (verification.state === 'missing'
                    ? 'Not verified'
                    : verification.state === 'unavailable'
                      ? 'Unavailable'
                      : 'Not loaded')}
              </Badge>
            </div>
            {verification.value ? (
              <>
                <p>{verificationReasons[verification.value.reason]}</p>
                <p>
                  {new Date(verification.value.at).toLocaleString()} ·{' '}
                  {verification.value.actor}
                </p>
              </>
            ) : (
              <p>
                Verification assesses the recorded execution only. It does not
                collect fresh evidence or re-execute the action.
              </p>
            )}
            <p className="bank-alert">
              Incident resolution: NOT_DETERMINED. Execution success,
              service_down, partial evidence and verification never establish
              recovery.
            </p>
            {execution.value?.status === 'RUNNING' && (
              <p>
                Verifying RUNNING produces an immutable inconclusive snapshot
                that cannot be overwritten after completion.
              </p>
            )}
            <button
              className="button"
              disabled={!canVerify}
              onClick={() => setConfirmation('verify')}
            >
              Verify recorded execution
            </button>
          </section>
          <section className="bank-panel">
            <h2>Backend audit history</h2>
            <p>
              Read-only events returned by the authorized backend. No fabricated
              audit actor or event is added.
            </p>
            <ol className="incident-timeline">
              {proposal.audit.map((a) => (
                <li key={a.event}>
                  <strong>Proposal · {a.event}</strong>
                  <time>{new Date(a.at).toLocaleString()}</time>
                  <small>Actor: {a.actor}</small>
                </li>
              ))}
              {execution.value?.audit.map((a) => (
                <li key={a.event}>
                  <strong>Execution · {a.event}</strong>
                  <time>{new Date(a.at).toLocaleString()}</time>
                  <small>
                    Actor is not supplied by this execution-audit API.
                  </small>
                </li>
              ))}
            </ol>
            {verification.value && (
              <p>
                Verification record:{' '}
                {new Date(verification.value.at).toLocaleString()} ·
                human_reviewer. The API does not expose a separate
                verification-audit feed.
              </p>
            )}
            <p className="monitor-caption">
              Snapshots are independent reads and may change between requests.
              Persistence and audit immutability are enforced by the backend;
              this UI provides no edit/delete action.
            </p>
          </section>
        </>
      )}
      <Dialog
        open={!!confirmation && active}
        dismissible={!busy}
        onClose={() => setConfirmation(null)}
        title="Confirm governance action"
      >
        <div className="bank-form">
          <p>
            Action: {confirmation}. Proposal: {proposal?.id}.
          </p>
          <p>
            {proposal && actions[proposal.action]} ·{' '}
            {confirmation === 'execute'
              ? 'Fixed parameter: service=banking-service'
              : confirmation === 'verify'
                ? 'Basis: recorded_execution; incident resolution remains NOT_DETERMINED'
                : `Reason: ${decisionReasons[reason]}`}
          </p>
          <p>
            This writes a durable backend record. No automatic retry will occur.
            Review the evidence and exact approved action before confirming.
          </p>
          {confirmation === 'execute' && (
            <p>
              Only the two allowlisted read-only operations can run, and only if
              execution is already enabled on the backend.
            </p>
          )}
          <button
            className="button button-primary"
            disabled={busy || locked}
            onClick={() => void submit()}
          >
            {busy ? 'Submitting…' : 'Confirm action'}
          </button>
        </div>
      </Dialog>
    </div>
  )
}
