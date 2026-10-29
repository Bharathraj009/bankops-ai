import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Banking from '../pages/Banking'
import {
  amount,
  api,
  money,
  transferBody,
  setOperatorCredential,
} from '../banking'
beforeEach(() => setOperatorCredential('isolated-operator-ui-regression-only'))
const source = '11111111-1111-4111-8111-111111111111'
const destination = '22222222-2222-4222-8222-222222222222'
const account = {
  id: source,
  accountNumber: 'TEST-ONLY',
  currency: 'USD',
  balance: '1000.00',
  createdAt: '2026-01-01T00:00:00Z',
}
const history = {
  transactions: [],
  page: 0,
  size: 10,
  totalElements: 0,
  totalPages: 0,
}
function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}
describe('banking integration', () => {
  it.each([400, 401, 403, 404, 409, 422, 500, 503])(
    'returns safe errors for HTTP %s without retrying',
    async (status) => {
      const fetch = vi
        .fn()
        .mockResolvedValue(
          response({ message: 'sensitive SQL and credentials' }, status),
        )
      vi.stubGlobal('fetch', fetch)
      await expect(api('/accounts/test')).rejects.not.toThrow(
        /sensitive SQL|credentials/,
      )
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
  it('allowlists response fields and rejects malformed service data', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          response({
            ...account,
            requestHash: 'private',
            idempotencyKey: 'private',
          }),
        )
        .mockResolvedValueOnce(response({ ...account, balance: 'NaN' })),
    )
    expect(await api('/accounts/test')).toEqual(account)
    await expect(api('/accounts/test')).rejects.toThrow(
      'Invalid service response',
    )
  })
  it('cancels an unsubmitted review without sending a write', async () => {
    const fetch = vi.fn(async (url: string) =>
      response(url.includes('/transactions') ? history : account),
    )
    vi.stubGlobal('fetch', fetch)
    render(<Banking />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Account ID'), source)
    await user.click(screen.getByRole('button', { name: 'Load account' }))
    await screen.findByText('No completed transactions for this account.')
    await user.type(
      screen.getByLabelText('Destination account ID'),
      destination,
    )
    await user.type(screen.getByLabelText('Amount (USD)'), '1.00')
    await user.click(screen.getByRole('button', { name: 'Review transfer' }))
    await user.click(
      screen.getByRole('button', { name: 'Close confirm transfer' }),
    )
    expect(screen.getByLabelText('Amount (USD)')).not.toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('validates amounts without floating point rounding', () => {
    for (const invalid of [
      '0',
      '-1',
      '1e2',
      '0.001',
      'NaN',
      '01',
      '100000000000000000',
    ])
      expect(amount(invalid)).toBe(false)
    expect(amount('0.01')).toBe(true)
    expect(money('99999999999999999.99')).toBe('$99,999,999,999,999,999.99')
    expect(transferBody(source, destination, '99999999999999999.99')).toContain(
      '"amount":99999999999999999.99',
    )
    expect(() => transferBody(source, source, '10')).toThrow()
  })
  it('preserves large backend financial decimal tokens', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify(account).replace(
              '"1000.00"',
              '99999999999999999.99',
            ),
          ),
        ),
    )
    expect(await api('/accounts/test')).toMatchObject({
      balance: '99999999999999999.99',
    })
  })
  it('loads real account data and ledger history, handles unknown accounts safely', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(account))
      .mockResolvedValueOnce(response(history))
      .mockResolvedValueOnce(response({ secret: 'SQL DETAILS' }, 404))
    vi.stubGlobal('fetch', fetch)
    render(<Banking />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Account ID'), source)
    await user.click(screen.getByRole('button', { name: 'Load account' }))
    expect(
      await screen.findByText('No completed transactions for this account.'),
    ).toBeInTheDocument()
    expect(screen.getAllByText('$1,000.00').length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: 'Refresh account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Record not found',
    )
    expect(screen.queryByText(/SQL DETAILS/)).not.toBeInTheDocument()
  })
  it('requires review, prevents duplicate clicks and reuses the exact key after uncertain failure', async () => {
    const writes: RequestInit[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === 'POST') {
          writes.push(init)
          throw new TypeError('network lost')
        }
        return response(_url.includes('/transactions') ? history : account)
      }),
    )
    render(<Banking />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Account ID'), source)
    await user.click(screen.getByRole('button', { name: 'Load account' }))
    await screen.findByText('No completed transactions for this account.')
    await user.type(
      screen.getByLabelText('Destination account ID'),
      destination,
    )
    await user.type(screen.getByLabelText('Amount (USD)'), '250.00')
    await user.click(screen.getByRole('button', { name: /Review transfer/ }))
    expect(writes).toHaveLength(0)
    const confirm = screen.getByRole('button', {
      name: 'Confirm / retry same transfer',
    })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    await waitFor(() => expect(writes).toHaveLength(1))
    await waitFor(() => expect(confirm).not.toBeDisabled())
    await user.click(confirm)
    await waitFor(() => expect(writes).toHaveLength(2))
    expect(writes[0].body).toBe(writes[1].body)
    expect(writes[0].headers).toEqual(writes[1].headers)
    expect(screen.getByLabelText('Amount (USD)')).toBeDisabled()
  })
  it('creates only zero-balance USD accounts through the existing API', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({ ...account, balance: '0.00' }, 201))
      .mockResolvedValueOnce(response({ ...account, balance: '0.00' }))
      .mockResolvedValueOnce(response(history))
    vi.stubGlobal('fetch', fetch)
    render(<Banking />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await user.type(screen.getByLabelText('Account number'), 'TEST-ONLY')
    await user.click(
      screen.getByRole('button', { name: 'Create zero-balance account' }),
    )
    await screen.findByText('Account created with zero opening balance.')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      accountNumber: 'TEST-ONLY',
      currency: 'USD',
    })
  })
})
