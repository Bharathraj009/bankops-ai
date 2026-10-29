import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from '@playwright/test'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
test.use({ trace: 'off', video: 'off' })
function fixture() {
  if (process.env.BANKOPS_SYNTHETIC_GOVERNANCE !== 'step61-local-only')
    throw new Error('Explicit isolated governance opt-in required')
  return JSON.parse(
    readFileSync(resolve('.cache/step61/session.json'), 'utf8'),
  ) as { proposer: string; reviewer: string; ids: Record<string, string> }
}
async function credential(page: Page, token: string, role = 'reviewer') {
  await page.getByLabel('Workspace role').selectOption(role)
  // Pass ephemeral secrets without fill() call-log arguments or Playwright tracing.
  await page.getByLabel('Bearer credential').evaluate((input, value) => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value',
    )!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  }, token)
  await page.getByRole('button', { name: 'Use credential' }).click()
}
async function load(page: Page, id: string) {
  await page.getByLabel('Proposal ID', { exact: true }).fill(id)
  await page.getByRole('button', { name: 'Load / refresh records' }).click()
  await expect(
    page.getByRole('button', { name: 'Load / refresh records' }),
  ).toBeEnabled()
}
async function confirm(page: Page, label: string) {
  await page.getByRole('button', { name: label, exact: true }).click()
  await page
    .getByRole('button', { name: 'Confirm action', exact: true })
    .click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
}
async function direct(
  request: APIRequestContext,
  path: string,
  token: string,
  data: unknown,
) {
  try {
    return await request.post(
      `http://127.0.0.1:18062/remediation/proposals/${path}`,
      { headers: { Authorization: `Bearer ${token}` }, data },
    )
  } catch {
    throw new Error('Isolated fixture request failed')
  }
}
test('isolated governance lifecycle and authorization', async ({
  page,
  request,
}) => {
  const f = fixture()
  const posts: string[] = []
  page.on('request', (r) => {
    if (r.method() === 'POST') posts.push(r.url())
  })
  await page.goto('/approvals')
  await credential(page, f.proposer, 'proposer')
  await load(page, f.ids.health)
  await expect(page.getByText('PENDING', { exact: true })).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Approve proposal' }),
  ).not.toBeVisible()
  expect(
    (
      await direct(request, `${f.ids.health}/approve`, f.proposer, {
        reason: 'reviewed_evidence',
      })
    ).status(),
  ).toBe(403)
  await page
    .getByRole('button', { name: 'Clear credential and records' })
    .click()
  await credential(page, f.proposer, 'reviewer')
  await load(page, f.ids.health)
  await confirm(page, 'Approve proposal')
  await expect(page.getByLabel('Bearer credential')).toHaveValue('')
  await expect(page.getByRole('alert')).toContainText('not authorized')
  await credential(page, f.reviewer)
  await load(page, f.ids.health)
  await confirm(page, 'Approve proposal')
  await load(page, f.ids.health)
  await confirm(page, 'Execute approved read-only action')
  await load(page, f.ids.health)
  await confirm(page, 'Verify recorded execution')
  await expect(
    page.getByText('EXECUTION_SUCCEEDED', { exact: true }),
  ).toBeVisible()
  expect(
    (
      await direct(request, `${f.ids.health}/execute`, f.reviewer, {
        action: 'CHECK_SERVICE_HEALTH',
        parameters: { service: 'banking-service' },
      })
    ).status(),
  ).toBe(409)
  expect(
    (
      await direct(request, `${f.ids.health}/verify`, f.reviewer, {
        basis: 'recorded_execution',
      })
    ).status(),
  ).toBe(409)
  await load(page, f.ids.evidence)
  await confirm(page, 'Approve proposal')
  await load(page, f.ids.evidence)
  await confirm(page, 'Execute approved read-only action')
  await load(page, f.ids.evidence)
  await confirm(page, 'Verify recorded execution')
  await expect(
    page.getByText('EXECUTION_SUCCEEDED', { exact: true }),
  ).toBeVisible()
  await load(page, f.ids.reject)
  await confirm(page, 'Reject proposal')
  await expect(
    page.getByText('REJECTED', { exact: true }).first(),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Execute approved read-only action' }),
  ).toBeDisabled()
  const concurrent = await Promise.all([
    direct(request, `${f.ids.reject}/approve`, f.reviewer, {
      reason: 'reviewed_evidence',
    }),
    direct(request, `${f.ids.reject}/reject`, f.reviewer, {
      reason: 'risk_unacceptable',
    }),
  ])
  expect(concurrent.map((r) => r.status())).toEqual([409, 409])
  const decisions = await Promise.all([
    direct(request, `${f.ids.race}/approve`, f.reviewer, {
      reason: 'reviewed_evidence',
    }),
    direct(request, `${f.ids.race}/reject`, f.reviewer, {
      reason: 'risk_unacceptable',
    }),
  ])
  expect(decisions.map((r) => r.status()).sort()).toEqual([200, 409])
  const dispatches = await Promise.all([
    direct(request, `${f.ids.concurrent}/execute`, f.reviewer, {
      action: 'CHECK_SERVICE_HEALTH',
      parameters: { service: 'banking-service' },
    }),
    direct(request, `${f.ids.concurrent}/execute`, f.reviewer, {
      action: 'CHECK_SERVICE_HEALTH',
      parameters: { service: 'banking-service' },
    }),
  ])
  expect(dispatches.map((r) => r.status()).sort()).toEqual([200, 409])
  await load(page, f.ids.running)
  await expect(page.getByText('RUNNING', { exact: true })).toBeVisible()
  await confirm(page, 'Verify recorded execution')
  await expect(
    page.getByText('VERIFICATION_INCONCLUSIVE', { exact: true }),
  ).toBeVisible()
  await load(page, f.ids.failed)
  await expect(page.getByText('FAILED', { exact: true })).toBeVisible()
  await confirm(page, 'Verify recorded execution')
  await expect(
    page.getByText('EXECUTION_FAILED', { exact: true }),
  ).toBeVisible()
  await load(page, f.ids.legacy)
  await expect(
    page.getByRole('button', { name: 'Execute approved read-only action' }),
  ).toBeDisabled()
  expect(
    (
      await direct(request, `${f.ids.legacy}/execute`, f.reviewer, {
        action: 'CHECK_SERVICE_HEALTH',
        parameters: { service: 'banking-service' },
      })
    ).status(),
  ).toBe(409)
  await expect(
    page.getByText(/Incident resolution: NOT_DETERMINED/),
  ).toBeVisible()
  expect(posts.every((url) => url.includes('/governance-api/'))).toBe(true)
  await page
    .getByRole('button', { name: 'Clear credential and records' })
    .click()
  await expect(page.getByLabel('Bearer credential')).toHaveValue('')
  expect(
    (await request.get('/governance-api/remediation/proposals')).status(),
  ).toBe(404)
})
test('isolated governance restart persistence', async ({ page }) => {
  const f = fixture()
  await page.goto('/remediation')
  await credential(page, f.reviewer)
  for (const [key, status] of [
    ['health', 'EXECUTION_SUCCEEDED'],
    ['evidence', 'EXECUTION_SUCCEEDED'],
    ['running', 'VERIFICATION_INCONCLUSIVE'],
    ['failed', 'EXECUTION_FAILED'],
  ]) {
    await load(page, f.ids[key])
    await expect(page.getByText(status, { exact: true })).toBeVisible()
    await expect(page.getByText(/Actor: human_reviewer/)).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Execute approved read-only action' }),
    ).toBeDisabled()
  }
  await page.screenshot({
    path: 'test-results/governance-isolated.png',
    fullPage: true,
  })
  await page
    .getByRole('button', { name: 'Clear credential and records' })
    .click()
})
