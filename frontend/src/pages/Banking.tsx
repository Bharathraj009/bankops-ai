import { useEffect, useRef, useState } from 'react'
import {
  ArrowDownLeft,
  ArrowUpRight,
  Landmark,
  Plus,
  RefreshCw,
} from 'lucide-react'
import { Dialog, Badge } from '../components/ui'
import {
  api,
  BankingError,
  money,
  transferBody,
  uuid,
  type Account,
  type History,
  type Transfer,
  setOperatorCredential,
  hasOperatorCredential,
} from '../banking'

export default function Banking({ active = true }: { active?: boolean }) {
  const [unlocked, setUnlocked] = useState(hasOperatorCredential)
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [lock, setLock] = useState(false)
  useEffect(() => {
    const clear = () => setUnlocked(false)
    window.addEventListener('bankops-operator-locked', clear)
    if (!active) {
      setOperatorCredential()
      queueMicrotask(clear)
    }
    return () => window.removeEventListener('bankops-operator-locked', clear)
  }, [active])
  useEffect(() => () => setOperatorCredential(), [])
  if (!unlocked)
    return (
      <section className="bank-panel">
        <Badge tone="blue">Operator workspace</Badge>
        <h2>Your banking workspace starts here</h2>
        <p>
          Operator credentials are required. Customer banking has a separate
          login and ownership boundary.
        </p>
        <a href="/customer">Open customer banking</a>
        <form
          className="bank-form"
          onSubmit={async (e) => {
            e.preventDefault()
            if (busy) return
            setBusy(true)
            setError('')
            const form = e.currentTarget
            const token = String(
              new FormData(form).get('operatorCredential') ?? '',
            )
            form.reset()
            try {
              setOperatorCredential(token)
              await api('/operator/me')
              setUnlocked(true)
            } catch {
              setOperatorCredential()
              setError('Operator authentication failed.')
            } finally {
              setBusy(false)
            }
          }}
        >
          <label>
            Operator credential
            <input
              name="operatorCredential"
              type="password"
              autoComplete="off"
              required
              minLength={32}
              maxLength={256}
            />
          </label>
          <button className="button button-primary" disabled={busy}>
            {busy ? 'Checking…' : 'Unlock operator workspace'}
          </button>
        </form>
        {error && <p role="alert">{error}</p>}
      </section>
    )
  return (
    <>
      <div className="bank-toolbar">
        <Badge tone="blue">Authenticated operator</Badge>
        <button className="button button-primary" onClick={() => setLock(true)}>
          Lock operator workspace
        </button>
      </div>
      <OperatorBanking active={active} />
      <Dialog
        open={lock}
        onClose={() => setLock(false)}
        title="Lock operator workspace"
      >
        <p>
          Credentials and loaded records will be cleared. If a transfer outcome
          is uncertain, verify history before submitting a new transfer after
          unlocking.
        </p>
        <button
          className="button button-primary"
          onClick={() => {
            setOperatorCredential()
            setUnlocked(false)
            setLock(false)
          }}
        >
          Lock and clear
        </button>
      </Dialog>
    </>
  )
}
function OperatorBanking({ active = true }: { active?: boolean }) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selected, setSelected] = useState<Account>()
  const [history, setHistory] = useState<History>()
  const [query, setQuery] = useState('')
  const [lookup, setLookup] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [create, setCreate] = useState(false)
  const [number, setNumber] = useState('')
  const [destination, setDestination] = useState('')
  const [value, setValue] = useState('')
  const [review, setReview] = useState(false)
  const [attempt, setAttempt] = useState<{
    body: string
    key: string
    submitted?: boolean
  }>()
  const [pending, setPending] = useState(false)
  const [direction, setDirection] = useState('ALL')
  const [search, setSearch] = useState('')
  const [detail, setDetail] = useState<Transfer>()
  const [transferId, setTransferId] = useState('')
  const busy = useRef(false)
  const readVersion = useRef(0)
  useEffect(() => {
    if (!attempt) return
    const unload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    const navigate = (e: MouseEvent) => {
      if ((e.target as Element).closest('a[href]')) {
        e.preventDefault()
        setError(
          'Resolve the current transfer attempt before leaving Banking. Its original retry key is retained on this page.',
        )
      }
    }
    window.addEventListener('beforeunload', unload)
    document.addEventListener('click', navigate, true)
    return () => {
      window.removeEventListener('beforeunload', unload)
      document.removeEventListener('click', navigate, true)
    }
  }, [attempt])
  const message = (e: unknown) =>
    setError(
      e instanceof BankingError
        ? e.message
        : 'Unable to complete the request. Check connectivity; an attempted write may have an unknown outcome.',
    )
  function remember(a: Account) {
    setAccounts((old) => [...old.filter((x) => x.id !== a.id), a])
    setSelected(a)
  }
  async function read(id: string, page = 0) {
    if (!uuid.test(id)) {
      setError('Enter a valid account UUID.')
      return
    }
    const version = ++readVersion.current
    setLoading(true)
    setError('')
    setHistory(undefined)
    try {
      const a = await api<Account>(`/accounts/${id}`)
      if (version !== readVersion.current) return
      remember(a)
      const h = await api<History>(
        `/accounts/${id}/transactions?page=${page}&size=10`,
      )
      if (version === readVersion.current) setHistory(h)
    } catch (e) {
      if (version === readVersion.current) message(e)
    } finally {
      if (version === readVersion.current) setLoading(false)
    }
  }
  async function createAccount() {
    if (busy.current) return
    busy.current = true
    setPending(true)
    setError('')
    try {
      const a = await api<Account>('/accounts', {
        method: 'POST',
        body: JSON.stringify({ accountNumber: number, currency: 'USD' }),
      })
      remember(a)
      setHistory(undefined)
      setCreate(false)
      setNumber('')
      setNotice('Account created with zero opening balance.')
      await read(a.id)
    } catch (e) {
      message(e)
    } finally {
      busy.current = false
      setPending(false)
    }
  }
  function prepare() {
    try {
      if (!selected) return
      const body = transferBody(selected.id, destination, value)
      setAttempt({ body, key: crypto.randomUUID() })
      setReview(true)
      setError('')
    } catch (e) {
      setError((e as Error).message)
    }
  }
  async function submit() {
    if (!attempt || busy.current) return
    busy.current = true
    setAttempt({ ...attempt, submitted: true })
    setPending(true)
    setError('')
    try {
      const t = await api<Transfer>('/transfers', {
        method: 'POST',
        body: attempt.body,
        headers: { 'Idempotency-Key': attempt.key },
      })
      setDetail(t)
      setReview(false)
      setAttempt(undefined)
      setValue('')
      setDestination('')
      setNotice(
        'Transfer recorded. Refresh accounts to confirm the latest balances.',
      )
      await read(t.sourceAccountId)
    } catch (e) {
      message(e)
      if (e instanceof BankingError && [400, 404, 422].includes(e.status)) {
        setAttempt(undefined)
        setReview(false)
      }
    } finally {
      busy.current = false
      setPending(false)
    }
  }
  const visible = accounts.filter((a) =>
    `${a.accountNumber} ${a.id}`.toLowerCase().includes(query.toLowerCase()),
  )
  return (
    <div className="banking-workspace">
      <section className="banking-banner">
        <div>
          <span className="eyebrow">BANKING OPERATIONS</span>
          <h2>Every movement. Accounted for.</h2>
          <p>Live account records and ledger-derived transaction history.</p>
        </div>
        <button
          className="button button-primary"
          onClick={() => setCreate(true)}
          disabled={pending || !!attempt}
        >
          <Plus size={17} /> Create account
        </button>
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
          <div>
            <h2>Account directory</h2>
            <p>
              Accounts loaded in this session. The service does not provide a
              global account list.
            </p>
          </div>
          <Badge>{accounts.length} loaded</Badge>
        </div>
        <form
          className="bank-toolbar"
          onSubmit={(e) => {
            e.preventDefault()
            void read(lookup)
          }}
        >
          <label>
            Account ID
            <input
              required
              value={lookup}
              onChange={(e) => setLookup(e.target.value.trim())}
              placeholder="Enter account UUID"
            />
          </label>
          <button
            className="button button-primary"
            disabled={loading || !!attempt}
          >
            Load account
          </button>
          <label>
            Search loaded accounts
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Account number or ID"
            />
          </label>
        </form>
        {!accounts.length ? (
          <div className="bank-empty">
            <Landmark size={30} />
            <h3>Your banking workspace starts here</h3>
            <p>
              Load an existing account by ID or create a new zero-balance
              account.
            </p>
          </div>
        ) : (
          <div className="bank-table-wrap">
            <table>
              <caption className="sr-only">
                Accounts loaded this session
              </caption>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Currency</th>
                  <th>Last fetched balance</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <strong>{a.accountNumber}</strong>
                      <small>{a.id}</small>
                    </td>
                    <td>{a.currency}</td>
                    <td className="money">{money(a.balance)}</td>
                    <td>
                      <button
                        className="button"
                        disabled={loading || !!attempt}
                        onClick={() => void read(a.id)}
                      >
                        Open account
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!visible.length && <p>No loaded accounts match your search.</p>}
          </div>
        )}
      </section>
      {loading && (
        <div role="status" className="skeleton bank-loading">
          Loading account and history…
        </div>
      )}
      {selected && (
        <>
          <div className="bank-grid">
            <section className="bank-panel balance-card">
              <Badge tone="blue">{selected.currency} ACCOUNT</Badge>
              <h2>{selected.accountNumber}</h2>
              <span className="bank-balance">{money(selected.balance)}</span>
              <p>Last fetched balance · refresh to confirm current funds</p>
              <small className="bank-id">{selected.id}</small>
              <p>Created {new Date(selected.createdAt).toLocaleString()}</p>
              <button
                className="button"
                disabled={loading || !!attempt}
                onClick={() => void read(selected.id)}
              >
                <RefreshCw size={15} /> Refresh account
              </button>
            </section>
            <section className="bank-panel">
              <h2>Move money</h2>
              <p>
                USD transfers are committed atomically by the banking service.
              </p>
              <form
                className="bank-form"
                onSubmit={(e) => {
                  e.preventDefault()
                  prepare()
                }}
              >
                <label>
                  Source account
                  <input readOnly value={selected.id} />
                </label>
                <label>
                  Destination account ID
                  <input
                    required
                    disabled={!!attempt}
                    value={destination}
                    onChange={(e) => setDestination(e.target.value.trim())}
                  />
                </label>
                <label>
                  Amount (USD)
                  <input
                    required
                    disabled={!!attempt}
                    inputMode="decimal"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    placeholder="0.00"
                  />
                </label>
                {attempt ? (
                  <button
                    type="button"
                    className="button button-primary"
                    onClick={() => setReview(true)}
                  >
                    Review existing attempt
                  </button>
                ) : (
                  <button className="button button-primary" disabled={loading}>
                    Review transfer <ArrowUpRight size={16} />
                  </button>
                )}
              </form>
            </section>
          </div>
          <section className="bank-panel">
            <div className="section-heading">
              <div>
                <h2>Ledger-backed activity</h2>
                <p>Completed incoming and outgoing transfers, newest first.</p>
              </div>
            </div>
            <div className="bank-toolbar">
              <label>
                Direction (this page)
                <select
                  value={direction}
                  onChange={(e) => setDirection(e.target.value)}
                >
                  <option value="ALL">All directions</option>
                  <option>INCOMING</option>
                  <option>OUTGOING</option>
                </select>
              </label>
              <label>
                Search transfer ID (this page)
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
            </div>
            {history ? (
              <>
                <div className="bank-table-wrap">
                  <table>
                    <caption className="sr-only">
                      Completed transaction history
                    </caption>
                    <thead>
                      <tr>
                        <th>Transfer / timestamp</th>
                        <th>Direction</th>
                        <th>Amount</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.transactions
                        .filter(
                          (t) =>
                            (direction === 'ALL' ||
                              t.direction === direction) &&
                            t.transferId.includes(search),
                        )
                        .map((t) => (
                          <tr key={t.transferId}>
                            <td>
                              <button
                                className="bank-link"
                                onClick={() => {
                                  setError('')
                                  void api<Transfer>(
                                    `/transfers/${t.transferId}`,
                                  )
                                    .then(setDetail)
                                    .catch(message)
                                }}
                              >
                                {t.transferId}
                              </button>
                              <small>
                                {new Date(t.timestamp).toLocaleString()}
                              </small>
                            </td>
                            <td>
                              {t.direction === 'INCOMING' ? (
                                <ArrowDownLeft size={14} />
                              ) : (
                                <ArrowUpRight size={14} />
                              )}{' '}
                              {t.direction}
                            </td>
                            <td className="money">{money(t.amount)}</td>
                            <td>
                              <Badge>{t.status}</Badge>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                {!history.transactions.length && (
                  <div className="bank-empty">
                    No completed transactions for this account.
                  </div>
                )}
                {history.transactions.length > 0 &&
                  !history.transactions.some(
                    (t) =>
                      (direction === 'ALL' || t.direction === direction) &&
                      t.transferId.includes(search),
                  ) && (
                    <p role="status">
                      No transactions match the filters on this page.
                    </p>
                  )}
                <div className="bank-pagination">
                  <span>
                    {history.totalElements} transactions · Page{' '}
                    {history.page + 1} of {Math.max(1, history.totalPages)}
                  </span>
                  <button
                    className="button"
                    disabled={loading || history.page === 0 || !!attempt}
                    onClick={() => void read(selected.id, history.page - 1)}
                  >
                    Previous
                  </button>
                  <button
                    className="button"
                    disabled={
                      loading ||
                      history.page + 1 >= history.totalPages ||
                      !!attempt
                    }
                    onClick={() => void read(selected.id, history.page + 1)}
                  >
                    Next
                  </button>
                </div>
              </>
            ) : (
              !loading && <p>History is unavailable. Refresh to load it.</p>
            )}
          </section>
        </>
      )}
      <section className="bank-panel">
        <h2>Find a transfer</h2>
        <form
          className="bank-toolbar"
          onSubmit={(e) => {
            e.preventDefault()
            if (!uuid.test(transferId)) {
              setError('Enter a valid transfer UUID.')
              return
            }
            setError('')
            void api<Transfer>(`/transfers/${transferId}`)
              .then(setDetail)
              .catch(message)
          }}
        >
          <label>
            Transfer ID
            <input
              required
              value={transferId}
              onChange={(e) => setTransferId(e.target.value.trim())}
            />
          </label>
          <button className="button">Find transfer</button>
        </form>
      </section>
      <Dialog
        open={create && active}
        dismissible={!pending}
        onClose={() => {
          if (!pending) setCreate(false)
        }}
        title="Create account"
      >
        <form
          className="bank-form"
          onSubmit={(e) => {
            e.preventDefault()
            void createAccount()
          }}
        >
          <p>
            A new USD account starts at $0.00. No opening balance can be
            supplied.
          </p>
          <label>
            Account number
            <input
              data-autofocus
              required
              maxLength={64}
              pattern={'.*\\S.*'}
              value={number}
              onChange={(e) => setNumber(e.target.value)}
            />
          </label>
          <button disabled={pending} className="button button-primary">
            {pending ? 'Creating…' : 'Create zero-balance account'}
          </button>
        </form>
      </Dialog>
      <Dialog
        open={review && active}
        dismissible={!pending}
        onClose={() => {
          if (!pending) {
            setReview(false)
            if (!attempt?.submitted) setAttempt(undefined)
          }
        }}
        title="Confirm transfer"
      >
        <div className="bank-form">
          <p>Review carefully. This action moves real funds.</p>
          <dl>
            <dt>From</dt>
            <dd>{selected?.id}</dd>
            <dt>To</dt>
            <dd>{destination}</dd>
            <dt>Amount</dt>
            <dd className="bank-balance">{value && money(value)} USD</dd>
          </dl>
          <p>
            Retries reuse this exact request and its original idempotency key.
            No automatic retries. Keep this page open if the outcome is unknown.
          </p>
          {error && <p role="alert">{error}</p>}
          <button
            className="button button-primary"
            disabled={pending}
            onClick={() => void submit()}
          >
            {pending ? 'Submitting…' : 'Confirm / retry same transfer'}
          </button>
        </div>
      </Dialog>
      <Dialog
        open={!!detail && active}
        onClose={() => setDetail(undefined)}
        title="Transfer details"
      >
        {detail && (
          <dl className="bank-details">
            {(
              [
                'id',
                'sourceAccountId',
                'destinationAccountId',
                'amount',
                'currency',
                'status',
                'createdAt',
              ] as const
            ).map((k) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{k === 'amount' ? money(detail[k]) : detail[k]}</dd>
              </div>
            ))}
          </dl>
        )}
      </Dialog>
    </div>
  )
}
