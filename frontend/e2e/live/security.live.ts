import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

test('actual agent reviewer boundary and browser credential isolation', async ({
  page,
  request,
}) => {
  if (process.env.BANKOPS_SECURITY_E2E !== 'step66-isolated')
    throw Error('Isolated security harness required')
  const f = JSON.parse(process.env.BANKOPS_SECURITY_SESSION!)
  const base = 'http://127.0.0.1:18067/remediation/proposals'
  const proposal = await request.post(base, {
    headers: { Authorization: `Bearer ${f.proposer}` },
    data: {
      action: 'CHECK_SERVICE_HEALTH',
      evidence_references: ['rule.banking_unavailable'],
    },
  })
  expect(proposal.status()).toBe(201)
  const id = (await proposal.json()).proposal_id
  for (const token of [f.operator, f.deployment, 'malformed']) {
    expect(
      (
        await request.get(`${base}/${id}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
      ).status(),
    ).toBe(401)
  }
  expect(
    (
      await request.post(`${base}/${id}/approve`, {
        headers: { Authorization: `Bearer ${f.proposer}` },
        data: { reason: 'reviewed_evidence' },
      })
    ).status(),
  ).toBe(403)
  expect(
    (
      await request.post(base, {
        headers: { Authorization: `Bearer ${f.reviewer}` },
        data: {
          action: 'CHECK_SERVICE_HEALTH',
          evidence_references: ['rule.banking_unavailable'],
        },
      })
    ).status(),
  ).toBe(403)
  await page.goto('/approvals')
  await page.getByLabel('Workspace role').selectOption('reviewer')
  await page.getByLabel('Bearer credential').evaluate((input, value) => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value',
    )!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  }, f.reviewer)
  await page.getByRole('button', { name: 'Use credential' }).click()
  await page.getByLabel('Proposal ID', { exact: true }).fill(id)
  await page
    .getByRole('button', { name: 'Load / refresh records', exact: true })
    .click()
  await expect(page.getByText('PENDING', { exact: true })).toBeVisible()
  await page
    .getByRole('button', { name: 'Approve proposal', exact: true })
    .click()
  await page
    .getByRole('button', { name: 'Confirm action', exact: true })
    .click()
  await expect(page.getByText('APPROVED', { exact: true })).toBeVisible()
  expect(
    (
      await request.post(`${base}/${id}/reject`, {
        headers: { Authorization: `Bearer ${f.reviewer}` },
        data: { reason: 'risk_unacceptable' },
      })
    ).status(),
  ).toBe(409)
  const audit = await request.get(`${base}/${id}`, {
    headers: { Authorization: `Bearer ${f.reviewer}` },
  })
  expect(
    (await audit.json()).audit.map((event: { actor: string }) => event.actor),
  ).toEqual(['proposal_service', 'human_reviewer'])
  const storage = await page.evaluate(() =>
    JSON.stringify([localStorage, sessionStorage]),
  )
  for (const token of Object.values(f))
    if (typeof token === 'string') expect(storage.includes(token)).toBe(false)
  await page.goto('/customer')
  await page.goto('/approvals')
  await expect(page.getByLabel('Bearer credential')).toHaveValue('')
  expect((await request.get('/api/v1/operator/me')).status()).toBe(401)
  const logs = await readFile(
    process.env.BANKOPS_SECURITY_LOG_DIR! + '/agent-service.log',
    'utf8',
  )
  for (const token of Object.values(f))
    if (typeof token === 'string') expect(logs.includes(token)).toBe(false)
  expect(
    (
      await request.post('/customer-api/register', {
        headers: { Origin: 'https://attacker.invalid' },
        data: {},
      })
    ).status(),
  ).toBe(403)
})
