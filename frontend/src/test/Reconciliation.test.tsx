import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import Reconciliation from '../pages/Reconciliation'
import { assessment, loadAirflow, parseAirflow } from '../reconciliation'
import { airflowFixture } from './airflowFixture'
afterEach(() => vi.useRealTimers())
const mock = (data: unknown) => {
  const fetch = vi.fn(async () => new Response(JSON.stringify(data)))
  vi.stubGlobal('fetch', fetch)
  return fetch
}
describe('reconciliation evidence', () => {
  it('orders observations newest first and accepts only timestamp fields', () => {
    const d = airflowFixture()
    const older = {
      ...d.airflow.runs[0],
      observed_at: new Date(Date.now() - 7200000).toISOString(),
    }
    d.airflow.runs.unshift(older)
    expect(parseAirflow(d)!.runs.map((r) => r.observed_at)).toEqual([
      d.airflow.runs[1].observed_at,
      older.observed_at,
    ])
    d.airflow.runs[0].observed_at = 'October 16, 2026 01:00:00Z'
    expect(() => parseAirflow(d)).toThrow()
  })
  it('uses recorded daily results without treating an hour-old run as stale collection', () => {
    const a = parseAirflow(airflowFixture())
    expect(assessment(a, Date.now())).toBe('PASS')
    expect(assessment(a, Date.now() + 61000)).toBe('INSUFFICIENT_DATA')
    expect(assessment(a, Date.now(), true)).toBe('Unavailable')
  })
  it.each([
    'partial',
    'missing',
    'unavailable',
    'timeout',
    'invalid_response',
    'disabled',
  ])('never passes %s collection', (status) => {
    const d = airflowFixture()
    d.airflow.status = status
    expect(assessment(parseAirflow(d), Date.now())).toBe('INSUFFICIENT_DATA')
  })
  it('keeps null, truncated and empty evidence insufficient', () => {
    expect(assessment(parseAirflow({ airflow: null }), Date.now())).toBe(
      'INSUFFICIENT_DATA',
    )
    const d = airflowFixture()
    d.airflow.truncated = true
    expect(assessment(parseAirflow(d), Date.now())).toBe('INSUFFICIENT_DATA')
    d.airflow.truncated = false
    d.airflow.runs = []
    expect(assessment(parseAirflow(d), Date.now())).toBe('INSUFFICIENT_DATA')
  })
  it('projects safe fields and rejects unsupported or inconsistent conclusions', () => {
    const d = airflowFixture()
    const poisoned = {
      ...d,
      airflow: {
        ...d.airflow,
        credentials: 'SECRET',
        runs: d.airflow.runs.map((r) => ({ ...r, message: 'ACCOUNT-SECRET' })),
      },
    }
    expect(JSON.stringify(parseAirflow(poisoned))).not.toMatch(
      /SECRET|credentials|message/,
    )
    d.airflow.runs[0].checks[0].violations = 1
    expect(() => parseAirflow(d)).toThrow()
  })
  it.each([
    'tasks',
    'checks',
    'outcome',
    'date',
    'count',
    'future',
    'duplicate',
  ])('rejects malformed %s', (kind) => {
    const d = airflowFixture(),
      r = d.airflow.runs[0]
    if (kind === 'tasks') r.tasks[0].task = 'private-value'
    if (kind === 'checks') r.checks[0].rule = 'private-value'
    if (kind === 'outcome') r.outcome = 'resolved'
    if (kind === 'date') r.observed_at = 'not a date'
    if (kind === 'count') r.checks[0].violations = -1
    if (kind === 'future')
      r.observed_at = new Date(Date.now() + 100000).toISOString()
    if (kind === 'duplicate') r.tasks[1] = { ...r.tasks[0] }
    expect(() => parseAirflow(d)).toThrow()
  })
  it('distinguishes checker findings from task failures and incomplete checks', () => {
    const d = airflowFixture(),
      r = d.airflow.runs[0]
    r.state = 'failed'
    r.outcome = 'task_failure'
    expect(assessment(parseAirflow(d), Date.now())).toBe('Task failure')
    r.outcome = 'financial_violations'
    r.summary_status = 'FAIL'
    r.checks[0].violations = 1
    expect(assessment(parseAirflow(d), Date.now())).toBe('FAIL')
    r.outcome = 'insufficient_data'
    r.summary_status = 'INSUFFICIENT_DATA'
    r.checks = []
    expect(assessment(parseAirflow(d), Date.now())).toBe('INSUFFICIENT_DATA')
  })
  it('renders, filters, reviews task/check evidence and refreshes only on request', async () => {
    const fetch = mock(airflowFixture())
    render(<Reconciliation />)
    await screen.findByText('Observed DAG runs')
    expect(fetch).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: /Review run/ }))
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'Read-only connectivity',
    )
    expect(screen.getByRole('dialog')).toHaveTextContent('0 violations')
    fireEvent.click(
      screen.getByRole('button', { name: 'Close reconciliation run details' }),
    )
    fireEvent.change(screen.getByLabelText('Result filter'), {
      target: { value: 'task_failure' },
    })
    expect(screen.getByText('No runs match this filter')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }))
    fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence' }))
    await screen.findByRole('button', { name: 'Refresh evidence' })
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[0]).toEqual([
      '/reconciliation-api/incidents/detect',
      expect.objectContaining({ method: 'GET', credentials: 'omit' }),
    ])
  })
  it('expires a loaded collection without any automatic network retry', async () => {
    vi.useFakeTimers()
    const fetch = mock(airflowFixture())
    render(<Reconciliation />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(screen.getByText('Observed DAG runs')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(65000))
    expect(screen.getByText(/Stale evidence —/)).toBeInTheDocument()
    expect(screen.getAllByText('INSUFFICIENT_DATA').length).toBeGreaterThan(0)
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('handles missing configuration and failed requests without raw errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw Error('private password')
      }),
    )
    render(<Reconciliation />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Evidence request failed',
    )
    expect(document.body).not.toHaveTextContent('private password')
  })
  it('bounds payloads before parsing and rejects HTTP errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('x'.repeat(524289))),
    )
    await expect(loadAirflow(new AbortController().signal)).rejects.toThrow()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('secret', { status: 503 })),
    )
    await expect(loadAirflow(new AbortController().signal)).rejects.toThrow(
      'Evidence unavailable',
    )
  })
})
