import {
  BankingError,
  publicResponse,
  uuid,
  type Account,
  type History,
} from './banking'
export interface Customer {
  id: string
  username: string
}
export interface CustomerAccounts {
  accounts: Account[]
  page: number
  size: number
  totalElements: number
  totalPages: number
}
export interface CustomerTransfer {
  id: string
  sourceAccountId: string
  amount: string
  currency: 'USD'
  status: string
  createdAt: string
}
const fail = () => {
  throw new Error('Invalid customer service response')
}
const object = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return fail()
  return value as Record<string, unknown>
}
export class CustomerClient {
  private generation = 0
  private token?: string
  expiresAt?: string
  clear() {
    this.generation++
    this.token = undefined
    this.expiresAt = undefined
  }
  async request(path: string, init: RequestInit = {}): Promise<unknown> {
    const generation = this.generation
    if (
      !/^\/(register|login|logout|me|accounts(?:\/[0-9a-f-]+(?:\/transactions)?)?|transfers(?:\/[0-9a-f-]+)?)(?:\?page=\d+&size=\d+)?$/i.test(
        path,
      )
    )
      return fail()
    const response = await fetch('/customer-api' + path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        ...init.headers,
      },
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(15000),
    })
    if (!response.ok) {
      if ([401, 403].includes(response.status)) this.clear()
      throw new BankingError(response.status)
    }
    if (response.status === 204) return null
    const reader = response.body?.getReader()
    if (!reader) return fail()
    const chunks: Uint8Array[] = []
    let length = 0
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        length += value.length
        if (length > 524288) return fail()
        chunks.push(value)
      }
    } finally {
      await reader.cancel()
    }
    const bytes = new Uint8Array(length)
    let offset = 0
    for (const chunk of chunks) {
      bytes.set(chunk, offset)
      offset += chunk.length
    }
    if (generation !== this.generation) throw new BankingError(401)
    return JSON.parse(
      new TextDecoder()
        .decode(bytes)
        .replace(/("(?:balance|amount)"\s*:\s*)(-?\d+(?:\.\d+)?)/g, '$1"$2"'),
    )
  }
  private customer(value: unknown): Customer {
    const c = object(value)
    if (
      typeof c.id !== 'string' ||
      !uuid.test(c.id) ||
      typeof c.username !== 'string' ||
      !/^[a-z0-9][a-z0-9._-]{2,63}$/.test(c.username)
    )
      return fail()
    return { id: c.id, username: c.username }
  }
  async register(username: string, password: string) {
    return this.customer(
      await this.request('/register', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    )
  }
  async login(username: string, password: string) {
    this.clear()
    const generation = this.generation
    const s = object(
      await this.request('/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    )
    if (
      typeof s.token !== 'string' ||
      !/^cus_[A-Za-z0-9_-]{43}$/.test(s.token) ||
      typeof s.expiresAt !== 'string' ||
      !Number.isFinite(Date.parse(s.expiresAt))
    )
      return fail()
    if (generation !== this.generation) return fail()
    this.token = s.token
    this.expiresAt = s.expiresAt
    try {
      return this.customer(await this.request('/me'))
    } catch (e) {
      this.clear()
      throw e
    }
  }
  async logout() {
    try {
      await this.request('/logout', { method: 'POST', body: '{}' })
    } finally {
      this.clear()
    }
  }
  async accounts(page = 0): Promise<CustomerAccounts> {
    const r = object(await this.request(`/accounts?page=${page}&size=10`))
    if (
      !Array.isArray(r.accounts) ||
      r.accounts.length > 100 ||
      !['page', 'size', 'totalElements', 'totalPages'].every(
        (k) => Number.isSafeInteger(r[k]) && (r[k] as number) >= 0,
      )
    )
      return fail()
    return {
      accounts: r.accounts.map((a) => publicResponse('/account', a) as Account),
      page: r.page as number,
      size: r.size as number,
      totalElements: r.totalElements as number,
      totalPages: r.totalPages as number,
    }
  }
  async create() {
    return publicResponse(
      '/account',
      await this.request('/accounts', { method: 'POST', body: '{}' }),
    ) as Account
  }
  async account(id: string) {
    return publicResponse(
      '/account',
      await this.request('/accounts/' + id),
    ) as Account
  }
  async history(id: string, page = 0) {
    return publicResponse(
      '/accounts/transactions',
      await this.request(`/accounts/${id}/transactions?page=${page}&size=10`),
    ) as History
  }
  async transfer(body: string, key: string): Promise<CustomerTransfer> {
    const r = object(
      await this.request('/transfers', {
        method: 'POST',
        body,
        headers: { 'Idempotency-Key': key },
      }),
    )
    if (
      typeof r.id !== 'string' ||
      !uuid.test(r.id) ||
      typeof r.sourceAccountId !== 'string' ||
      !uuid.test(r.sourceAccountId) ||
      typeof r.amount !== 'string' ||
      !/^\d{1,17}(?:\.\d{1,2})?$/.test(r.amount) ||
      r.currency !== 'USD' ||
      !['PENDING', 'COMPLETED', 'FAILED'].includes(String(r.status)) ||
      typeof r.createdAt !== 'string' ||
      !Number.isFinite(Date.parse(r.createdAt))
    )
      return fail()
    return {
      id: r.id,
      sourceAccountId: r.sourceAccountId,
      amount: r.amount,
      currency: 'USD',
      status: String(r.status),
      createdAt: r.createdAt,
    }
  }
}
