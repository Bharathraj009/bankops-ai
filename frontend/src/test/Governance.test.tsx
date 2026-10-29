import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Governance from '../pages/Governance'
import {
  governanceRequest,
  parseProposal,
  parseExecution,
  parseVerification,
} from '../governance'
import {
  proposalFixture,
  executionFixture,
  verificationFixture,
  governanceId,
} from './governanceFixture'
const token = 'synthetic-unit-only-credential-not-valid-on-any-service'
function mount() {
  render(
    <MemoryRouter>
      <Governance active remediation={false} />
    </MemoryRouter>,
  )
}
function connect(role = 'reviewer') {
  fireEvent.change(screen.getByLabelText('Workspace role'), {
    target: { value: role },
  })
  fireEvent.change(screen.getByLabelText('Bearer credential'), {
    target: { value: token },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Use credential' }))
  fireEvent.change(screen.getByLabelText('Proposal ID'), {
    target: { value: governanceId },
  })
  fireEvent.click(
    screen.getByRole('button', { name: 'Load / refresh records' }),
  )
}
function mock(status = 'PENDING', ex: unknown = null, v: unknown = null) {
  const fetch = vi.fn(async (url: string) =>
    url.endsWith('/execution')
      ? new Response(ex ? JSON.stringify(ex) : '', { status: ex ? 200 : 404 })
      : url.endsWith('/verification')
        ? new Response(v ? JSON.stringify(v) : '', { status: v ? 200 : 404 })
        : new Response(JSON.stringify(proposalFixture(status))),
  )
  vi.stubGlobal('fetch', fetch)
  return fetch
}
describe('human governance workspace', () => {
  it('performs no requests before credential and ID submission and stores no credential', async () => {
    const fetch = mock()
    mount()
    expect(fetch).not.toHaveBeenCalled()
    connect()
    await screen.findByText('PENDING')
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    fireEvent.click(
      screen.getByRole('button', { name: 'Clear credential and records' }),
    )
    expect(screen.getByLabelText('Bearer credential')).toHaveValue('')
    expect(screen.queryByText('PENDING')).not.toBeInTheDocument()
  })
  it('requires explicit confirmation, prevents duplicate decisions and locks until read', async () => {
    const fetch = mock()
    mount()
    connect()
    await screen.findByText('PENDING')
    fireEvent.click(screen.getByRole('button', { name: 'Approve proposal' }))
    expect(fetch).toHaveBeenCalledTimes(3)
    fetch.mockResolvedValue(
      new Response(JSON.stringify(proposalFixture('APPROVED'))),
    )
    const confirm = screen.getByRole('button', { name: 'Confirm action' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    await screen.findByText('APPROVED')
    expect(fetch).toHaveBeenCalledTimes(4)
    expect(
      (fetch.mock.calls[3] as unknown as [string, RequestInit])[1].body,
    ).toBe('{"reason":"reviewed_evidence"}')
    expect(
      screen.getByRole('button', { name: 'Execute approved read-only action' }),
    ).toBeDisabled()
  })
  it('keeps proposer workspace read-only even with a pending proposal', async () => {
    mock()
    mount()
    connect('proposer')
    await screen.findByText('PENDING')
    expect(
      screen.queryByRole('button', { name: 'Approve proposal' }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Execute approved read-only action' }),
    ).toBeDisabled()
    expect(
      screen.getByText(/separately held human reviewer credential/),
    ).toBeInTheDocument()
  })
  it.each([401, 403])(
    'clears credentials and authorized records on HTTP %s',
    async (status) => {
      const fetch = mock()
      mount()
      connect()
      await screen.findByText('PENDING')
      fetch.mockResolvedValue(new Response('SECRET', { status }))
      fireEvent.click(
        screen.getByRole('button', { name: 'Load / refresh records' }),
      )
      await screen.findByRole('alert')
      expect(screen.getByLabelText('Bearer credential')).toHaveValue('')
      expect(screen.queryByText('PENDING')).not.toBeInTheDocument()
      expect(screen.queryByText('SECRET')).not.toBeInTheDocument()
    },
  )
  it('distinguishes failed execution lookup from missing and prevents dispatch', async () => {
    const fetch = mock('APPROVED')
    fetch.mockImplementation(async (url: string) =>
      url.endsWith('/execution')
        ? new Response('private', { status: 503 })
        : url.endsWith('/verification')
          ? new Response('', { status: 404 })
          : new Response(JSON.stringify(proposalFixture('APPROVED'))),
    )
    mount()
    connect()
    await screen.findByText('APPROVED')
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: 'Execute approved read-only action',
        }),
      ).toBeDisabled(),
    )
    expect(
      screen.getByText('Execution lookup failed. Absence cannot be inferred.'),
    ).toBeInTheDocument()
  })
  it('uses exact approved action and fixed parameters for execution', async () => {
    const fetch = mock('APPROVED')
    mount()
    connect()
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: 'Execute approved read-only action',
        }),
      ).not.toBeDisabled(),
    )
    fireEvent.click(
      screen.getByRole('button', { name: 'Execute approved read-only action' }),
    )
    fetch.mockResolvedValue(new Response(JSON.stringify(executionFixture())))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm action' }))
    await screen.findByText('SUCCEEDED')
    expect(
      (fetch.mock.calls[3] as unknown as [string, RequestInit])[1].body,
    ).toBe(
      '{"action":"CHECK_SERVICE_HEALTH","parameters":{"service":"banking-service"}}',
    )
    expect(screen.getAllByText(/NOT_DETERMINED/).length).toBeGreaterThan(0)
  })
  it('shows RUNNING and immutable inconclusive verification without recovery claims', async () => {
    mock(
      'APPROVED',
      executionFixture('RUNNING'),
      verificationFixture('VERIFICATION_INCONCLUSIVE', 'execution_incomplete'),
    )
    mount()
    connect()
    await screen.findByText('VERIFICATION_INCONCLUSIVE')
    expect(screen.getByText('RUNNING')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Verify recorded execution' }),
    ).toBeDisabled()
    expect(
      screen.getByText(/cannot be overwritten after completion/),
    ).toBeInTheDocument()
  })
  it('handles concurrency conflicts without automatic mutation retries', async () => {
    const fetch = mock()
    mount()
    connect()
    await screen.findByText('PENDING')
    fireEvent.click(screen.getByRole('button', { name: 'Reject proposal' }))
    fetch.mockResolvedValue(new Response('private', { status: 409 }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm action' }))
    await screen.findByRole('alert')
    expect(fetch).toHaveBeenCalledTimes(4)
    expect(
      screen.getByRole('button', { name: 'Approve proposal' }),
    ).toBeDisabled()
  })
  it('cancels before dispatch and rejects legacy execution actions', async () => {
    const fetch = mock()
    mount()
    connect()
    await screen.findByText('PENDING')
    fireEvent.click(screen.getByRole('button', { name: 'Reject proposal' }))
    fireEvent.click(
      screen.getByRole('button', { name: 'Close confirm governance action' }),
    )
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(
      parseProposal(proposalFixture('APPROVED', 'restart_banking_service'))
        .action,
    ).toBe('restart_banking_service')
  })
  it('rejects unsafe actors, invalid audit histories and resolution claims', () => {
    expect(() =>
      parseProposal({ ...proposalFixture(), created_by: 'private person' }),
    ).toThrow()
    expect(() => parseProposal({ ...proposalFixture(), audit: [] })).toThrow()
    expect(() =>
      parseExecution({
        ...executionFixture(),
        parameters: { service: 'arbitrary' },
      }),
    ).toThrow()
    expect(() =>
      parseVerification({
        ...verificationFixture(),
        incident_resolution: 'RESOLVED',
      }),
    ).toThrow()
    expect(
      JSON.stringify(
        parseProposal({ ...proposalFixture(), credentials: 'SECRET' }),
      ),
    ).not.toContain('SECRET')
  })
  it.each([400, 404, 409, 503])(
    'returns safe HTTP %s errors without retry',
    async (status) => {
      const fetch = vi
        .fn()
        .mockResolvedValue(new Response('password SECRET', { status }))
      vi.stubGlobal('fetch', fetch)
      await expect(
        governanceRequest(
          'proposal',
          governanceId,
          token,
          new AbortController().signal,
        ),
      ).rejects.not.toThrow(/SECRET|password/)
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
})
