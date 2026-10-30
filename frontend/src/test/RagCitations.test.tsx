import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { parseReport } from '../incidents'
import Incidents from '../pages/Incidents'
import { incidentFixture, reportFixture } from './incidentFixture'

function grounded() {
  const raw = JSON.parse(JSON.stringify(reportFixture()))
  const id = `doc.guide.${'a'.repeat(12)}.c000`
  raw.rca.retrieval = {
    status: 'matched',
    sources: [
      {
        id,
        document_id: 'guide',
        sha256: 'a'.repeat(64),
        reviewed: true,
        source: 'corpus://synthetic/guide',
        category: 'troubleshooting',
        title: 'Synthetic reviewed runbook',
        content:
          'Synthetic troubleshooting context <script>untrusted()</script>',
        supports: ['http_error_degradation'],
      },
    ],
  }
  raw.rca.hypotheses[0].retrieved_sources = [id]
  return raw
}

describe('RAG citation boundary', () => {
  it('renders reviewed citations as escaped text without outbound links', async () => {
    const raw = grounded()
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async (url: string) =>
          new Response(
            JSON.stringify(url.endsWith('/detect') ? incidentFixture() : raw),
          ),
      ),
    )
    render(
      <MemoryRouter>
        <Incidents active investigation />
      </MemoryRouter>,
    )
    await screen.findByRole('button', { name: /^HTTP errors/ })
    fireEvent.click(screen.getByRole('button', { name: 'Run AI RCA' }))
    fireEvent.click(
      screen.getByRole('button', { name: 'Confirm AI investigation' }),
    )
    const title = await screen.findByText('Synthetic reviewed runbook')
    fireEvent.click(title)
    expect(
      screen.getByText(raw.rca.retrieval.sources[0].content),
    ).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
    expect(document.querySelector('a[href^="corpus:"]')).toBeNull()
  })
  it('hides unreviewed local document title and body', () => {
    const raw = grounded()
    raw.rca.retrieval.sources[0].reviewed = false
    const report = parseReport(raw, true)
    expect(report.rca?.sources[0].title).toBe('Unreviewed local document')
    expect(report.rca?.sources[0].content).toBe(
      'Content hidden pending publication review.',
    )
  })
  it.each(['url', 'citation', 'support', 'hash', 'duplicate'])(
    'rejects invalid %s references',
    (mode) => {
      const raw = grounded(),
        source = raw.rca.retrieval.sources[0]
      if (mode === 'url') source.source = 'https://private.invalid/data'
      if (mode === 'citation')
        raw.rca.hypotheses[0].retrieved_sources = ['invented']
      if (mode === 'support') source.supports = ['latency_degradation']
      if (mode === 'hash') source.sha256 = 'b'.repeat(64)
      if (mode === 'duplicate') raw.rca.retrieval.sources.push(source)
      expect(() => parseReport(raw, true)).toThrow()
    },
  )
})
