import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import Monitoring from '../pages/Monitoring'
import {
  formatMetric,
  health,
  monitoringGet,
  observed,
  parseSnapshot,
} from '../monitoring'
import { monitoringFixture } from './monitoringFixture'
afterEach(() => vi.useRealTimers())
function mock(data = monitoringFixture()) {
  const fetch = vi.fn(
    async (url: string) =>
      new Response(
        JSON.stringify(
          url.endsWith('/health')
            ? { status: 'ok', service: 'bankops-reliability-agent' }
            : data,
        ),
      ),
  )
  vi.stubGlobal('fetch', fetch)
  return fetch
}
describe('read-only monitoring', () => {
  it('distinguishes observed zero, missing and invalid evidence', () => {
    const data = monitoringFixture()
    const snapshot = parseSnapshot(data),
      now = Date.now()
    expect(observed(snapshot, 'transfer_failure_rate', now)).toBe(0)
    expect(formatMetric('transfer_failure_rate', 0)).toBe('0')
    expect(formatMetric('api_error_rate', null)).toBe('—')
    expect(health(snapshot, now, false)).toBe('Healthy')
    snapshot.metrics[0].status = 'missing'
    snapshot.metrics[0].value = null
    expect(health(snapshot, now, false)).toBe('Insufficient data')
    expect(health(snapshot, now, true)).toBe('Unavailable')
    expect(health(parseSnapshot(data), now + 61000, false)).toBe(
      'Insufficient data',
    )
  })
  it('distinguishes unavailable banking and degraded rules', () => {
    const s = parseSnapshot(monitoringFixture())
    s.metrics.find((m) => m.name === 'banking_availability')!.value = 0
    expect(health(s, Date.now(), false)).toBe('Unavailable')
    s.metrics.find((m) => m.name === 'banking_availability')!.value = 1
    s.rules[1].state = 'incident'
    s.state = 'incident'
    expect(health(s, Date.now(), false)).toBe('Degraded')
  })
  it.each(['duplicate', 'negative', 'NaN', 'labels', 'missing-rule', 'future'])(
    'handles %s evidence safely',
    (kind) => {
      const d = monitoringFixture()
      if (kind === 'duplicate')
        d.evidence.metrics[1] = { ...d.evidence.metrics[0] }
      if (kind === 'negative') d.evidence.metrics[0].value = -1
      if (kind === 'NaN') d.evidence.metrics[0].value = NaN
      if (kind === 'labels')
        Object.assign(d, {
          credentials: 'do-not-render',
          internal_url: 'http://private',
        })
      if (kind === 'missing-rule') d.rules.pop()
      if (kind === 'future') {
        d.evidence.evaluated_at = new Date(Date.now() + 600000).toISOString()
        expect(health(parseSnapshot(d), Date.now(), false)).toBe(
          'Insufficient data',
        )
        return
      }
      if (kind === 'labels') {
        expect(JSON.stringify(parseSnapshot(d))).not.toContain('do-not-render')
        return
      }
      expect(() => parseSnapshot(d)).toThrow()
    },
  )
  it('loads actual values, permits local range and signal selection, and sends GET only', async () => {
    const fetch = mock()
    render(<Monitoring />)
    await screen.findByText('Healthy')
    expect(
      screen.getByRole('region', { name: 'API request rate' }),
    ).toHaveTextContent(/20\s*req\/s/)
    expect(screen.getByText('Process responding')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Signal'), {
      target: { value: 'api_latency_p95' },
    })
    fireEvent.change(screen.getByLabelText('Local observation range'), {
      target: { value: '60' },
    })
    expect(
      screen.getByRole('group', { name: /API latency p95/ }),
    ).toBeInTheDocument()
    fireEvent.focus(screen.getByRole('button', { name: /200 ms/ }))
    expect(
      screen.getByRole('status', { name: 'Observation details' }),
    ).toHaveTextContent('200 ms')
    for (const [url, init] of fetch.mock.calls as unknown as [
      string,
      RequestInit,
    ][]) {
      expect(url).toMatch(/^\/monitoring-api\/(health|incidents\/detect)$/)
      expect(init.method).toBe('GET')
    }
  })
  it('retains cached evidence on failure without claiming healthy', async () => {
    const fetch = mock()
    render(<Monitoring />)
    await screen.findByText('Healthy')
    fetch.mockRejectedValue(new Error('secret endpoint'))
    fireEvent.click(screen.getByRole('button', { name: 'Refresh now' }))
    await screen.findByText(/Banking health cannot be inferred/)
    expect(screen.queryByText('Healthy')).not.toBeInTheDocument()
    expect(screen.queryByText(/secret endpoint/)).not.toBeInTheDocument()
    expect(screen.getByText(/Stale or cached/)).toBeInTheDocument()
  })
  it('refreshes on the selected interval and expires data with refresh off', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
    const fetch = mock()
    render(<Monitoring />)
    await screen.findByText('Healthy')
    fireEvent.change(screen.getByLabelText('Auto refresh'), {
      target: { value: '15' },
    })
    await act(async () => {
      vi.advanceTimersByTime(15000)
    })
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(4))
    fireEvent.change(screen.getByLabelText('Auto refresh'), {
      target: { value: '0' },
    })
    await act(async () => {
      vi.advanceTimersByTime(65000)
    })
    expect(screen.getByText(/Stale or cached/)).toBeInTheDocument()
    expect(screen.queryByText('Healthy')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(4)
  })
  it('handles evidence failures independently from process health', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/health'))
          return new Response(
            '{"status":"ok","service":"bankops-reliability-agent"}',
          )
        throw new Error('unavailable')
      }),
    )
    render(<Monitoring />)
    await screen.findByText('Process responding')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Monitoring evidence is unavailable',
    )
  })
  it('sanitizes HTTP errors and honors cancellation', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(new Response('secret database', { status: 503 })),
    )
    await expect(
      monitoringGet('health', new AbortController().signal),
    ).rejects.toThrow('Monitoring source unavailable')
    const fetch = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) =>
          init.signal!.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          ),
        ),
    )
    vi.stubGlobal('fetch', fetch)
    const { unmount } = render(<Monitoring />)
    unmount()
    expect(fetch.mock.calls.every((c) => c[1].signal?.aborted)).toBe(true)
  })
})
