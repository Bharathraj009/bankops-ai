export interface Account {
  id: string
  accountNumber: string
  currency: string
  balance: string
  createdAt: string
}
export interface Transfer {
  id: string
  sourceAccountId: string
  destinationAccountId: string
  amount: string
  currency: string
  status: string
  createdAt: string
}
export interface Transaction {
  transferId: string
  timestamp: string
  direction: string
  amount: string
  currency: string
  status: string
}
export interface History {
  transactions: Transaction[]
  page: number
  size: number
  totalElements: number
  totalPages: number
}
export const uuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export function amount(value: string) {
  if (!/^(0|[1-9]\d{0,16})(\.\d{1,2})?$/.test(value)) return false
  const [whole, fraction = ''] = value.split('.')
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0')) > 0n
}
export function money(value: string) {
  const [whole, fraction = ''] = value.split('.')
  return `$${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')}`
}
export class BankingError extends Error {
  constructor(public status: number) {
    super(
      status === 404
        ? 'Record not found.'
        : status === 422
          ? 'Transfer rejected. Check available funds and account limits.'
          : status === 409
            ? 'Conflict: this account number or request key is already in use.'
            : status === 401 || status === 403
              ? 'Access denied.'
              : status === 400
                ? 'Check the supplied details.'
                : 'Service unavailable. The request outcome may be unknown.',
    )
  }
}
let operatorCredential: string | undefined
export function setOperatorCredential(value?: string) {
  operatorCredential = value
}
export function hasOperatorCredential() {
  return !!operatorCredential
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(operatorCredential
        ? { Authorization: `Bearer ${operatorCredential}` }
        : {}),
      ...init?.headers,
    },
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
    signal: AbortSignal.timeout(15000),
  })
  if (!response.ok) {
    if ([401, 403].includes(response.status)) {
      operatorCredential = undefined
      window.dispatchEvent(new Event('bankops-operator-locked'))
    }
    throw new BankingError(response.status)
  }
  // Preserve decimal JSON tokens before JavaScript can round financial values.
  const text = await response.text()
  const result = JSON.parse(
    text.replace(/("(?:balance|amount)"\s*:\s*)(-?\d+(?:\.\d+)?)/g, '$1"$2"'),
  )
  if (path === '/operator/me') {
    if (result?.role !== 'OPERATOR') throw new Error('Invalid service response')
    return { role: 'OPERATOR' } as T
  }
  return publicResponse(path, result) as T
}
export function publicResponse(path: string, raw: unknown): unknown {
  const fail = () => {
    throw new Error('Invalid service response')
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return fail()
  const r = raw as Record<string, unknown>
  const text = (key: string) => {
    if (typeof r[key] !== 'string') return fail()
    return r[key] as string
  }
  const id = (key: string) => {
    const value = text(key)
    if (!uuid.test(value)) return fail()
    return value
  }
  const decimal = (key: string) => {
    const value = text(key)
    if (!/^(0|[1-9]\d{0,16})(\.\d{1,2})?$/.test(value)) return fail()
    return value
  }
  const timestamp = (key: string) => {
    const value = text(key)
    if (!Number.isFinite(Date.parse(value))) return fail()
    return value
  }
  if (path.includes('/transactions')) {
    if (
      !Array.isArray(r.transactions) ||
      r.transactions.length > 100 ||
      !['page', 'size', 'totalElements', 'totalPages'].every(
        (k) => Number.isSafeInteger(r[k]) && (r[k] as number) >= 0,
      )
    )
      return fail()
    return {
      transactions: r.transactions.map((item) =>
        publicResponse('/history-item', item),
      ),
      page: r.page,
      size: r.size,
      totalElements: r.totalElements,
      totalPages: r.totalPages,
    }
  }
  if (text('currency') !== 'USD') return fail()
  if (path === '/history-item') {
    if (
      !['INCOMING', 'OUTGOING'].includes(text('direction')) ||
      text('status') !== 'COMPLETED'
    )
      return fail()
    return {
      transferId: id('transferId'),
      timestamp: timestamp('timestamp'),
      direction: r.direction,
      amount: decimal('amount'),
      currency: 'USD',
      status: 'COMPLETED',
    }
  }
  if (path.startsWith('/transfers')) {
    if (!['PENDING', 'COMPLETED', 'FAILED'].includes(text('status')))
      return fail()
    return {
      id: id('id'),
      sourceAccountId: id('sourceAccountId'),
      destinationAccountId: id('destinationAccountId'),
      amount: decimal('amount'),
      currency: 'USD',
      status: r.status,
      createdAt: timestamp('createdAt'),
    }
  }
  const number = text('accountNumber')
  if (!number.trim() || number.length > 64) return fail()
  return {
    id: id('id'),
    accountNumber: number,
    currency: 'USD',
    balance: decimal('balance'),
    createdAt: timestamp('createdAt'),
  }
}
export function transferBody(
  sourceAccountId: string,
  destinationAccountId: string,
  value: string,
) {
  if (
    !uuid.test(sourceAccountId) ||
    !uuid.test(destinationAccountId) ||
    sourceAccountId.toLowerCase() === destinationAccountId.toLowerCase() ||
    !amount(value)
  )
    throw new Error(
      'Use distinct account IDs and a positive USD amount with at most two decimals.',
    )
  return `{"sourceAccountId":${JSON.stringify(sourceAccountId)},"destinationAccountId":${JSON.stringify(destinationAccountId)},"amount":${value}}`
}
