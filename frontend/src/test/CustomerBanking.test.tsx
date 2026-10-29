import { afterEach, describe, it, expect, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CustomerBanking from '../pages/CustomerBanking'
import Banking from '../pages/Banking'
import { CustomerClient } from '../customer'
import { setOperatorCredential } from '../banking'
const id = '11111111-1111-4111-8111-111111111111',
  destination = '22222222-2222-4222-8222-222222222222'
const customer = {
  id: '33333333-3333-4333-8333-333333333333',
  username: 'alpha_user',
}
const token = 'cus_' + 'a'.repeat(43)
const account = {
  id,
  accountNumber: 'MY-ACCOUNT',
  balance: 1000,
  currency: 'USD',
  createdAt: '2026-01-01T00:00:00Z',
}
const history = {
  transactions: [],
  page: 0,
  size: 10,
  totalElements: 0,
  totalPages: 0,
}
afterEach(() => vi.useRealTimers())
function mock() {
  let transfers = 0,
    expired = false
  const fetch = vi.fn(async (input: string, init: RequestInit) => {
    const path = input.replace('/customer-api', '').replace('/api/v1', ''),
      method = init.method ?? 'GET'
    const response = (v: unknown, status = 200) =>
      new Response(status === 204 ? null : JSON.stringify(v), { status })
    if (path === '/operator/me') return response({ role: 'OPERATOR' })
    if (path === '/register') return response(customer, 201)
    if (path === '/login')
      return response({
        token,
        expiresAt: new Date(Date.now() + 900000).toISOString(),
      })
    if (expired) return response({ error: 'private upstream details' }, 401)
    if (path === '/me') return response(customer)
    if (path === '/logout') return response(null, 204)
    if (path.includes('/transactions')) return response(history)
    if (path.startsWith('/accounts?'))
      return response({
        accounts: [{ ...account, balance: transfers > 1 ? 750 : 1000 }],
        page: 0,
        size: 10,
        totalElements: 1,
        totalPages: 1,
      })
    if (path === '/accounts' && method === 'POST')
      return response({ ...account, balance: 0 }, 201)
    if (path === '/accounts/' + id)
      return response({ ...account, balance: transfers > 1 ? 750 : 1000 })
    if (path === '/transfers') {
      transfers++
      if (transfers === 1) return response({}, 503)
      return response({
        id: destination,
        sourceAccountId: id,
        amount: 250,
        currency: 'USD',
        status: 'COMPLETED',
        createdAt: '2026-01-01T00:00:00Z',
        recipientName: 'PRIVATE-RECIPIENT',
      })
    }
    return response({}, 404)
  })
  vi.stubGlobal('fetch', fetch)
  return {
    fetch,
    expire: () => {
      expired = true
    },
  }
}
function mount() {
  return render(
    <MemoryRouter>
      <CustomerBanking />
    </MemoryRouter>,
  )
}
function credentials() {
  fireEvent.change(screen.getByLabelText('Username'), {
    target: { value: 'alpha_user' },
  })
  fireEvent.change(screen.getByLabelText('Password'), {
    target: { value: 'test-password-portfolio' },
  })
}
async function login() {
  credentials()
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await screen.findByText('Customer · alpha_user')
  await screen.findByText('MY-ACCOUNT')
}
describe('customer identity and owned banking UI', () => {
  it('discards responses from a cleared session', async () => {
    let release!: (value: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            release = resolve
          }),
      ),
    )
    const client = new CustomerClient(),
      result = client.request('/accounts')
    client.clear()
    release(new Response(JSON.stringify({ private: 'old-session-data' })))
    await expect(result).rejects.toThrow('Access denied')
  })
  it('registers without credentials in storage and requires a separate sign-in', async () => {
    const { fetch } = mock()
    mount()
    fireEvent.click(
      screen.getByRole('button', { name: 'Create customer login' }),
    )
    credentials()
    fireEvent.click(screen.getByRole('button', { name: 'Register customer' }))
    await screen.findByText(
      'Registration complete. Sign in with your new credentials.',
    )
    expect(screen.getByLabelText('Password')).toHaveValue('')
    expect(fetch).toHaveBeenCalledTimes(1)
    await login()
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    expect(document.body).not.toHaveTextContent(token)
    expect(
      fetch.mock.calls.every(([, init]) => init.credentials === 'omit'),
    ).toBe(true)
  })
  it('uses only the customer token, selects owned history, and retries only the original confirmed write', async () => {
    setOperatorCredential('isolated-operator-key-not-a-customer-key')
    const { fetch } = mock()
    mount()
    await login()
    fireEvent.click(screen.getByRole('button', { name: /MY-ACCOUNT/ }))
    await screen.findByText('No completed transactions for this account.')
    fireEvent.change(screen.getByLabelText('Recipient account ID'), {
      target: { value: destination },
    })
    fireEvent.change(screen.getByLabelText('Amount (USD)'), {
      target: { value: '250.00' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: 'Review customer transfer' }),
    )
    expect(
      fetch.mock.calls.filter(([url]) => url.endsWith('/transfers')),
    ).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm transfer' }))
    await screen.findByRole('alert')
    expect(
      fetch.mock.calls.filter(([url]) => url.endsWith('/transfers')),
    ).toHaveLength(1)
    fireEvent.click(
      screen.getByRole('button', { name: 'Retry original request' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Confirm transfer' }))
    await screen.findByText('Transfer status: COMPLETED.')
    const writes = fetch.mock.calls.filter(([url]) =>
      url.endsWith('/transfers'),
    )
    expect(writes).toHaveLength(2)
    expect(writes[0][1].body).toBe(writes[1][1].body)
    expect(writes[0][1].headers).toEqual(writes[1][1].headers)
    expect((writes[0][1].headers as Record<string, string>).Authorization).toBe(
      'Bearer ' + token,
    )
    expect(document.body).not.toHaveTextContent('PRIVATE-RECIPIENT')
  })
  it('clears private views on authentication failure and explicitly revokes on logout', async () => {
    const setup = mock()
    mount()
    await login()
    setup.expire()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh my accounts' }))
    await screen.findByRole('button', { name: 'Sign in' })
    expect(screen.queryByText('MY-ACCOUNT')).not.toBeInTheDocument()
  })
  it('logout is confirmed and clears the authenticated view', async () => {
    const { fetch } = mock()
    mount()
    await login()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(
      fetch.mock.calls.filter(([url]) => url.endsWith('/logout')),
    ).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Sign out and clear' }))
    await screen.findByRole('button', { name: 'Sign in' })
    expect(
      fetch.mock.calls.filter(([url]) => url.endsWith('/logout')),
    ).toHaveLength(1)
  })
  it('rejects malformed sessions and refuses unsupported request paths', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              token: 'operator-key',
              expiresAt: new Date().toISOString(),
            }),
          ),
      ),
    )
    const client = new CustomerClient()
    await expect(client.login('alpha', 'password-test')).rejects.toThrow()
    await expect(client.request('/../api/v1/accounts')).rejects.toThrow()
  })
  it('operator UI requires explicit unlock and can be locked again', async () => {
    const { fetch } = mock()
    render(
      <MemoryRouter>
        <Banking />
      </MemoryRouter>,
    )
    expect(screen.queryByLabelText('Account ID')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Operator credential'), {
      target: { value: 'isolated-operator-key-entered-explicitly' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: 'Unlock operator workspace' }),
    )
    await screen.findByLabelText('Account ID')
    expect(
      (fetch.mock.calls[0][1].headers as Record<string, string>).Authorization,
    ).toBe('Bearer isolated-operator-key-entered-explicitly')
    fireEvent.click(
      screen.getByRole('button', { name: 'Lock operator workspace' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Lock and clear' }))
    await waitFor(() =>
      expect(screen.queryByLabelText('Account ID')).not.toBeInTheDocument(),
    )
  })
  it('expires the in-memory session without automatically submitting a write', async () => {
    vi.useFakeTimers()
    const { fetch } = mock()
    mount()
    credentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(screen.getByText('Customer · alpha_user')).toBeInTheDocument()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(905000)
    })
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(
      fetch.mock.calls.filter(([, init]) => init.method === 'POST'),
    ).toHaveLength(1)
  })
})
