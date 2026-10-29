import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Landmark, LockKeyhole, RefreshCw } from 'lucide-react'
import { Badge, Dialog } from '../components/ui'
import {
  amount,
  BankingError,
  money,
  transferBody,
  uuid,
  type Account,
  type History,
} from '../banking'
import {
  CustomerClient,
  type Customer,
  type CustomerAccounts,
  type CustomerTransfer,
} from '../customer'
type Attempt = {
  owner: string
  body: string
  key: string
  source: string
  destination: string
  amount: string
  submitted: boolean
}
export default function CustomerBanking() {
  const [client] = useState(() => new CustomerClient())
  const [identity, setIdentity] = useState<Customer>(),
    [signup, setSignup] = useState(false)
  const [accounts, setAccounts] = useState<CustomerAccounts>(),
    [selected, setSelected] = useState<Account>(),
    [history, setHistory] = useState<History>()
  const [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false)
  const [destination, setDestination] = useState(''),
    [value, setValue] = useState(''),
    [confirm, setConfirm] = useState(false),
    [logout, setLogout] = useState(false)
  const [attempt, setAttempt] = useState<Attempt>(),
    [receipt, setReceipt] = useState<CustomerTransfer>()
  const pending = useRef<Attempt | undefined>(undefined),
    guard = useRef(false)
  const clear = useCallback(() => {
    setIdentity(undefined)
    setAccounts(undefined)
    setSelected(undefined)
    setHistory(undefined)
    setReceipt(undefined)
    setAttempt(undefined)
    setDestination('')
    setValue('')
    setConfirm(false)
  }, [])
  const fail = (e: unknown) => {
    setError(
      e instanceof BankingError
        ? e.message
        : 'Service unavailable. A submitted request may have completed; verify history before creating another request.',
    )
    if (e instanceof BankingError && [401, 403].includes(e.status)) {
      clear()
      setNotice(
        'Session ended. Sign in again. No financial request will be retried automatically.',
      )
    }
  }
  useEffect(() => {
    const timer = setInterval(() => {
      if (client.expiresAt && Date.parse(client.expiresAt) <= Date.now()) {
        client.clear()
        clear()
        setNotice('Session expired. Sign in again to continue.')
      }
    }, 5000)
    return () => {
      clearInterval(timer)
      client.clear()
    }
  }, [client, clear])
  async function work(action: () => Promise<void>) {
    if (guard.current) return
    guard.current = true
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (e) {
      fail(e)
    } finally {
      guard.current = false
      setBusy(false)
    }
  }
  async function refresh(page = accounts?.page ?? 0) {
    setAccounts(await client.accounts(page))
    if (selected) {
      setSelected(await client.account(selected.id))
      setHistory(await client.history(selected.id))
    }
  }
  async function submitTransfer() {
    if (!attempt || attempt.owner !== identity?.id) return
    const current = { ...attempt, submitted: true }
    pending.current = current
    setAttempt(current)
    setConfirm(false)
    await work(async () => {
      try {
        const result = await client.transfer(current.body, current.key)
        setReceipt(result)
        pending.current = undefined
        setAttempt(undefined)
        setDestination('')
        setValue('')
        setNotice(`Transfer status: ${result.status}.`)
        await refresh()
      } catch (e) {
        if (e instanceof BankingError && [400, 404, 422].includes(e.status)) {
          current.submitted = false
          pending.current = current
          setAttempt({ ...current })
        }
        throw e
      }
    })
  }
  return (
    <div className="banking-workspace customer-workspace">
      <section className="banking-banner customer-banner">
        <div>
          <span className="eyebrow">PRIVATE CUSTOMER BANKING</span>
          <h2>Your accounts. Your control.</h2>
          <p>Secure access to your balances and ledger-backed activity.</p>
        </div>
        <Landmark size={36} aria-hidden="true" />
      </section>
      {error && (
        <p role="alert" className="bank-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="bank-notice">
          {notice}
        </p>
      )}
      {!identity ? (
        <section className="bank-panel customer-auth">
          <Badge tone="blue">
            <LockKeyhole size={13} /> Customer access
          </Badge>
          <h2>
            {signup
              ? 'Create your customer login'
              : 'Sign in to customer banking'}
          </h2>
          <p>
            Customer sessions last 15 minutes. Operator and reviewer credentials
            do not sign you in here.
          </p>
          <form
            className="bank-form"
            onSubmit={(e) => {
              e.preventDefault()
              const form = e.currentTarget
              const data = new FormData(form)
              const username = String(data.get('username')),
                password = String(data.get('password'))
              form.reset()
              void work(async () => {
                if (signup) {
                  await client.register(username, password)
                  setSignup(false)
                  setNotice(
                    'Registration complete. Sign in with your new credentials.',
                  )
                  return
                }
                clear()
                const person = await client.login(username, password)
                setIdentity(person)
                setNotice('')
                setAccounts(await client.accounts())
                if (pending.current?.owner === person.id)
                  setAttempt(pending.current)
                else pending.current = undefined
              })
            }}
          >
            <label>
              Username
              <input
                name="username"
                autoComplete="username"
                required
                minLength={3}
                maxLength={64}
                pattern="[a-z0-9][a-z0-9._-]{2,63}"
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete={signup ? 'new-password' : 'current-password'}
                required
                minLength={12}
                maxLength={72}
              />
            </label>
            <small>
              Use a lowercase alias (3–64 characters) and a password of at least
              12 characters, at most 72 UTF-8 bytes.
            </small>
            <button className="button button-primary" disabled={busy}>
              {busy ? 'Please wait…' : signup ? 'Register customer' : 'Sign in'}
            </button>
          </form>
          <button
            className="button customer-link"
            disabled={busy}
            onClick={() => {
              setSignup(!signup)
              setError('')
              setNotice('')
            }}
          >
            {signup ? 'Back to sign in' : 'Create customer login'}
          </button>
          <p>
            Need operator tools?{' '}
            <Link to="/banking">Open the separate operator workspace</Link>.
          </p>
        </section>
      ) : (
        <>
          <div className="bank-toolbar">
            <Badge tone="blue">Customer · {identity.username}</Badge>
            <span className="customer-session">
              Expires{' '}
              {client.expiresAt
                ? new Date(client.expiresAt).toLocaleTimeString()
                : '—'}
            </span>
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() => setLogout(true)}
            >
              Sign out
            </button>
            <button
              className="button"
              disabled={busy}
              onClick={() => void work(() => refresh())}
            >
              <RefreshCw size={15} />
              Refresh my accounts
            </button>
          </div>
          <div className="customer-grid">
            <section className="bank-panel">
              <div className="recon-toolbar">
                <h2>My USD accounts</h2>
                <button
                  className="button button-primary"
                  disabled={busy || !!attempt}
                  onClick={() =>
                    void work(async () => {
                      const created = await client.create()
                      setAccounts(await client.accounts())
                      setSelected(created)
                      setHistory(await client.history(created.id))
                      setNotice('Account opened with a zero balance.')
                    })
                  }
                >
                  Open USD account
                </button>
              </div>
              {!accounts ? (
                <div role="status" className="skeleton">
                  Loading accounts…
                </div>
              ) : !accounts.accounts.length ? (
                <p>No owned accounts yet. Open an account to get started.</p>
              ) : (
                <div className="customer-account-list">
                  {accounts.accounts.map((a) => (
                    <button
                      className={`customer-account ${selected?.id === a.id ? 'selected' : ''}`}
                      key={a.id}
                      disabled={busy || !!attempt}
                      onClick={() =>
                        void work(async () => {
                          setSelected(await client.account(a.id))
                          setHistory(await client.history(a.id))
                          setReceipt(undefined)
                        })
                      }
                    >
                      <span>
                        <strong>{a.accountNumber}</strong>
                        <small>{a.id}</small>
                      </span>
                      <strong>{money(a.balance)}</strong>
                    </button>
                  ))}
                </div>
              )}
              {accounts && (
                <div className="bank-toolbar">
                  <button
                    className="button"
                    disabled={busy || !!attempt || accounts.page === 0}
                    onClick={() => void work(() => refresh(accounts.page - 1))}
                  >
                    Previous accounts
                  </button>
                  <span>
                    Page {accounts.page + 1} of{' '}
                    {Math.max(1, accounts.totalPages)}
                  </span>
                  <button
                    className="button"
                    disabled={
                      busy ||
                      !!attempt ||
                      accounts.page + 1 >= accounts.totalPages
                    }
                    onClick={() => void work(() => refresh(accounts.page + 1))}
                  >
                    Next accounts
                  </button>
                </div>
              )}
            </section>
            <section className="bank-panel">
              <h2>Send a transfer</h2>
              <p>
                Debit only an account you own. Enter the recipient’s account ID;
                their private details are never displayed.
              </p>
              {selected ? (
                <>
                  <p>
                    From <strong>{selected.accountNumber}</strong> ·{' '}
                    {money(selected.balance)}
                  </p>
                  <form
                    className="bank-form"
                    onSubmit={(e) => {
                      e.preventDefault()
                      if (
                        !uuid.test(destination) ||
                        !amount(value) ||
                        destination === selected.id
                      ) {
                        setError(
                          'Enter a different valid destination account ID and a positive USD amount.',
                        )
                        return
                      }
                      const next = {
                        owner: identity.id,
                        source: selected.id,
                        destination,
                        amount: value,
                        key: crypto.randomUUID(),
                        body: transferBody(selected.id, destination, value),
                        submitted: false,
                      }
                      pending.current = next
                      setAttempt(next)
                      setConfirm(true)
                    }}
                  >
                    <label>
                      Recipient account ID
                      <input
                        value={destination}
                        onChange={(e) => setDestination(e.target.value)}
                        disabled={busy || !!attempt}
                        required
                      />
                    </label>
                    <label>
                      Amount (USD)
                      <input
                        inputMode="decimal"
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        disabled={busy || !!attempt}
                        required
                      />
                    </label>
                    <button
                      className="button button-primary"
                      disabled={busy || !!attempt}
                    >
                      Review customer transfer
                    </button>
                  </form>
                </>
              ) : (
                <p>Select one of your accounts to send a transfer.</p>
              )}
              {attempt && (
                <div className="customer-attempt">
                  <p>
                    {attempt.submitted
                      ? 'The original request is retained. Its outcome may be unknown; verify history or retry this exact request.'
                      : 'The request has not completed. You can retry or discard it.'}
                  </p>
                  <button
                    className="button button-primary"
                    disabled={busy}
                    onClick={() => setConfirm(true)}
                  >
                    Retry original request
                  </button>
                  {!attempt.submitted && (
                    <button
                      className="button"
                      disabled={busy}
                      onClick={() => {
                        pending.current = undefined
                        setAttempt(undefined)
                      }}
                    >
                      Discard uncompleted request
                    </button>
                  )}
                </div>
              )}
              {receipt && (
                <div role="status" className="customer-receipt">
                  <Badge>{receipt.status}</Badge>
                  <p>Transfer {receipt.id}</p>
                  <strong>{money(receipt.amount)}</strong>
                </div>
              )}
            </section>
          </div>
          <section className="bank-panel">
            <h2>My transaction history</h2>
            <p>
              Incoming and outgoing completed postings for the selected account.
              Counterparty information is withheld.
            </p>
            {!selected ? (
              <p>Select an account to view activity.</p>
            ) : !history ? (
              <p>No history loaded.</p>
            ) : (
              <>
                {!history.transactions.length ? (
                  <p>No completed transactions for this account.</p>
                ) : (
                  <div className="bank-table-wrap">
                    <table>
                      <caption className="sr-only">
                        My ledger-backed transaction history
                      </caption>
                      <thead>
                        <tr>
                          <th>Timestamp</th>
                          <th>Transfer ID</th>
                          <th>Direction</th>
                          <th>Amount</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {history.transactions.map((t) => (
                          <tr key={t.transferId}>
                            <td>{new Date(t.timestamp).toLocaleString()}</td>
                            <td>{t.transferId}</td>
                            <td>{t.direction}</td>
                            <td>{money(t.amount)}</td>
                            <td>
                              <Badge>{t.status}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="bank-toolbar">
                  <button
                    className="button"
                    disabled={busy || history.page === 0}
                    onClick={() =>
                      void work(async () =>
                        setHistory(
                          await client.history(selected.id, history.page - 1),
                        ),
                      )
                    }
                  >
                    Previous transactions
                  </button>
                  <span>
                    Page {history.page + 1} of {Math.max(1, history.totalPages)}
                  </span>
                  <button
                    className="button"
                    disabled={busy || history.page + 1 >= history.totalPages}
                    onClick={() =>
                      void work(async () =>
                        setHistory(
                          await client.history(selected.id, history.page + 1),
                        ),
                      )
                    }
                  >
                    Next transactions
                  </button>
                </div>
              </>
            )}
          </section>
        </>
      )}
      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Confirm customer transfer"
        dismissible={!busy}
      >
        {attempt && (
          <>
            <p>
              Send <strong>{money(attempt.amount)}</strong> USD from account{' '}
              {attempt.source} to the account ID you entered:{' '}
              {attempt.destination}?
            </p>
            <p>
              No recipient name or balance has been retrieved. Only this exact
              request will be sent.
            </p>
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() => void submitTransfer()}
            >
              Confirm transfer
            </button>
          </>
        )}
      </Dialog>
      <Dialog
        open={logout}
        onClose={() => setLogout(false)}
        title="Sign out of customer banking"
        dismissible={!busy}
      >
        <p>
          Your session will be revoked and displayed records cleared. If a
          transfer outcome is uncertain, verify its history before starting
          another transfer after signing in again.
        </p>
        <button
          className="button button-primary"
          disabled={busy}
          onClick={() =>
            void work(async () => {
              try {
                await client.logout()
              } finally {
                pending.current = undefined
                clear()
                setLogout(false)
                setNotice('Signed out.')
              }
            })
          }
        >
          Sign out and clear
        </button>
      </Dialog>
    </div>
  )
}
