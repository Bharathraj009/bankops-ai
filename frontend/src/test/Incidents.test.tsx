import { describe, expect, it, vi } from 'vitest'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Incidents from '../pages/Incidents'
import { incidentRequest, parseDetection, parseReport } from '../incidents'
import { incidentFixture, reportFixture } from './incidentFixture'
import { monitoringFixture } from './monitoringFixture'
function mount() {
  return render(
    <MemoryRouter initialEntries={['/incidents']}>
      <Incidents active investigation={false} />
    </MemoryRouter>,
  )
}
function mock() {
  const fetch = vi.fn(
    async (url: string) =>
      new Response(
        JSON.stringify(
          url.endsWith('/detect') ? incidentFixture() : reportFixture(),
        ),
      ),
  )
  vi.stubGlobal('fetch', fetch)
  return fetch
}
describe('incident investigation', () => {
  it('loads actual rule evaluations without inventing severity or incident history', async () => {
    const fetch = mock()
    mount()
    await screen.findByRole('button', { name: /^HTTP errors/ })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Not provided by API')).toBeInTheDocument()
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Evaluation filter'), {
      target: { value: 'all' },
    })
    expect(screen.getAllByRole('button', { name: /Within rule/ })).toHaveLength(
      3,
    )
    fireEvent.change(screen.getByLabelText('Search rules'), {
      target: { value: 'HTTP' },
    })
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: /^API p95/ }),
      ).not.toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: /^HTTP errors/ }))
    expect(
      await screen.findByRole('heading', {
        name: /HTTP errors.*observed details/,
      }),
    ).toBeInTheDocument()
  })
  it('collects facts and sanitized evidence without invoking AI', async () => {
    const fetch = mock()
    mount()
    await screen.findByRole('button', { name: /^HTTP errors/ })
    fireEvent.click(screen.getByRole('button', { name: 'Collect evidence' }))
    await screen.findByRole('heading', { name: 'Investigation evidence' })
    expect(
      screen.getByText(/Not requested. Observed evidence/),
    ).toBeInTheDocument()
    expect(screen.getByText('HTTP request completed')).toBeInTheDocument()
    expect(fetch.mock.calls.map((c) => c[0])).toEqual([
      '/investigation-api/incidents/detect',
      '/investigation-api/incidents/investigate',
    ])
  })
  it('requires explicit AI confirmation and prevents duplicate workflow submission', async () => {
    const fetch = mock()
    mount()
    await screen.findByRole('button', { name: /^HTTP errors/ })
    fireEvent.click(screen.getByRole('button', { name: 'Run AI RCA' }))
    expect(fetch).toHaveBeenCalledTimes(1)
    const confirm = screen.getByRole('button', {
      name: 'Confirm AI investigation',
    })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    await screen.findByText('Reported confidence: low')
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(
      (fetch.mock.calls[1] as unknown as [string, RequestInit])[1],
    ).toMatchObject({ method: 'POST' })
    expect(screen.getByText('Causality is unconfirmed')).toBeInTheDocument()
    expect(screen.getByText(/rule.high_http_error_rate/)).toBeInTheDocument()
  })
  it('distinguishes fresh no-incidents from insufficient evidence', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify(monitoringFixture())),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              ...monitoringFixture(),
              state: 'insufficient_data',
            }),
          ),
        ),
    )
    mount()
    await screen.findByText('No incidents detected in this fresh snapshot.')
    fireEvent.click(screen.getByRole('button', { name: 'Refresh detection' }))
    expect(
      await screen.findByText(
        'Insufficient evidence to establish that there are no incidents.',
      ),
    ).toBeInTheDocument()
  })
  it('keeps investigation failures separate from detection and never retries automatically', async () => {
    const fetch = mock()
    mount()
    await screen.findByRole('button', { name: /^HTTP errors/ })
    fetch.mockRejectedValue(new Error('PRIVATE URL credentials'))
    fireEvent.click(screen.getByRole('button', { name: 'Collect evidence' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Evidence investigation failed',
    )
    expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(screen.getByText('Degraded')).toBeInTheDocument()
  })
  it('shows unavailable detection independently from no incidents', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('secret', { status: 503 })),
    )
    mount()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Detection service unavailable',
    )
    expect(
      screen.queryByText('No incidents detected in this fresh snapshot.'),
    ).not.toBeInTheDocument()
  })
  it('preserves disabled RCA and partial evidence states', async () => {
    const r = reportFixture()
    r.evidence_status = 'partial'
    Object.assign(r.rca, {
      status: 'undetermined',
      reason: 'disabled',
      hypotheses: [],
      evidence: [],
    })
    const fetch = mock()
    fetch.mockResolvedValue(new Response(JSON.stringify(r)))
    const { EvidenceReport } = await import('../pages/Incidents')
    render(<EvidenceReport report={parseReport(r, true)} />)
    expect(screen.getByText('Undetermined')).toBeInTheDocument()
    expect(screen.getByText(/LLM inference is disabled/)).toBeInTheDocument()
    expect(screen.getByText('Partial evidence')).toBeInTheDocument()
  })
  it.each([
    'unknown-reference',
    'wrong-kind',
    'confidence',
    'confirmed',
    'raw-span',
    'bad-correlation',
    'bad-count',
    'timestamp',
  ])('rejects unsupported %s', (kind) => {
    const r = reportFixture()
    if (kind === 'unknown-reference')
      r.rca.hypotheses[0].supporting_evidence = ['rule.fake']
    if (kind === 'wrong-kind') r.rca.hypotheses[0].kind = 'latency_degradation'
    if (kind === 'confidence') r.rca.hypotheses[0].confidence = 'high'
    if (kind === 'confirmed') r.rca.root_cause_confirmed = true
    if (kind === 'raw-span')
      r.traces.traces[0].spans[0].name = '/accounts/private'
    if (kind === 'bad-correlation') r.correlations[0].log_event_indexes = [20]
    if (kind === 'bad-count') r.observed_facts.returned_trace_count = 99
    if (kind === 'timestamp') r.completed_at = 'private URL'
    expect(() => parseReport(r, true)).toThrow()
  })
  it('drops raw messages, prompts, credentials and arbitrary explanations', () => {
    const r = reportFixture()
    Object.assign(r, {
      prompt: 'PRIVATE',
      credentials: 'PRIVATE',
      possible_explanations: ['PRIVATE'],
    })
    Object.assign(r.logs.events[0], {
      message: 'PRIVATE',
      stack_trace: 'PRIVATE',
      account_number: 'PRIVATE',
    })
    expect(JSON.stringify(parseReport(r, true))).not.toContain('PRIVATE')
  })
  it('rejects contradictory triggered rules and aborts pending reads', async () => {
    expect(() =>
      parseDetection({ ...incidentFixture(), triggered_rules: [] }),
    ).toThrow()
    const c = new AbortController()
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url, init) =>
          new Promise((_resolve, reject) =>
            init.signal.addEventListener('abort', () =>
              reject(new Error('aborted')),
            ),
          ),
      ),
    )
    const p = incidentRequest('detect', c.signal)
    c.abort()
    await expect(p).rejects.toThrow()
  })
  it('does not run a workflow when the confirmation is canceled', async () => {
    const fetch = mock()
    mount()
    await screen.findByRole('button', { name: /^HTTP errors/ })
    fireEvent.click(screen.getByRole('button', { name: 'Run AI RCA' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'Close run ai root cause analysis',
      }),
    )
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
