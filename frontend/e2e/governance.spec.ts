import { test, expect } from '@playwright/test'
import {
  governanceId,
  proposalFixture,
  executionFixture,
  verificationFixture,
} from '../src/test/governanceFixture'
test.use({ trace: 'off' })
test('approval, explicit read-only execution, verification and safe conflict handling', async ({
  page,
}, info) => {
  let status = 'PENDING',
    executed = false,
    verified = false,
    posts = 0
  await page.route('**/governance-api/**', async (route) => {
    const r = route.request(),
      url = r.url()
    if (r.method() === 'POST') {
      posts++
      if (url.endsWith('/approve')) {
        if (status !== 'PENDING') {
          await route.fulfill({ status: 409 })
          return
        }
        status = 'APPROVED'
        await route.fulfill({ json: proposalFixture(status) })
        return
      }
      if (url.endsWith('/execute')) {
        expect(r.postDataJSON()).toEqual({
          action: 'CHECK_SERVICE_HEALTH',
          parameters: { service: 'banking-service' },
        })
        executed = true
        await route.fulfill({ json: executionFixture() })
        return
      }
      if (url.endsWith('/verify')) {
        expect(r.postDataJSON()).toEqual({ basis: 'recorded_execution' })
        verified = true
        await route.fulfill({ status: 201, json: verificationFixture() })
        return
      }
    }
    if (url.endsWith('/execution')) {
      await route.fulfill(
        executed ? { json: executionFixture() } : { status: 404 },
      )
      return
    }
    if (url.endsWith('/verification')) {
      await route.fulfill(
        verified ? { json: verificationFixture() } : { status: 404 },
      )
      return
    }
    await route.fulfill({ json: proposalFixture(status) })
  })
  await page.goto('/approvals')
  await page
    .getByLabel('Bearer credential')
    .fill('synthetic-browser-only-placeholder-not-a-real-credential')
  await page.getByRole('button', { name: 'Use credential' }).click()
  await page.getByLabel('Proposal ID', { exact: true }).fill(governanceId)
  await page.getByRole('button', { name: 'Load / refresh records' }).click()
  await expect(page.getByText('PENDING', { exact: true })).toBeVisible()
  expect(posts).toBe(0)
  await page.getByRole('button', { name: 'Approve proposal' }).click()
  expect(posts).toBe(0)
  await page.getByRole('button', { name: 'Confirm action' }).click()
  await expect(
    page.getByText('APPROVED', { exact: true }).first(),
  ).toBeVisible()
  expect(posts).toBe(1)
  await page.getByRole('button', { name: 'Load / refresh records' }).click()
  await expect(
    page.getByRole('button', { name: 'Execute approved read-only action' }),
  ).toBeEnabled()
  await page.getByRole('link', { name: 'Open remediation' }).click()
  await page
    .getByRole('button', { name: 'Execute approved read-only action' })
    .click()
  await page.getByRole('button', { name: 'Confirm action' }).click()
  await expect(page.getByText('SUCCEEDED', { exact: true })).toBeVisible()
  expect(posts).toBe(2)
  await page.getByRole('button', { name: 'Load / refresh records' }).click()
  await expect(
    page.getByRole('button', { name: 'Verify recorded execution' }),
  ).toBeEnabled()
  await page.getByRole('button', { name: 'Verify recorded execution' }).click()
  await page.getByRole('button', { name: 'Confirm action' }).click()
  await expect(
    page.getByText('EXECUTION_SUCCEEDED', { exact: true }),
  ).toBeVisible()
  expect(posts).toBe(3)
  await expect(
    page.getByText(/Incident resolution: NOT_DETERMINED/),
  ).toBeVisible()
  expect(
    await page.evaluate(() => localStorage.getItem('governance-credential')),
  ).toBeNull()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await page.screenshot({
    path: `test-results/governance-${info.project.name}.png`,
    fullPage: true,
  })
  await page
    .getByRole('button', { name: 'Clear credential and records' })
    .click()
  await expect(page.getByLabel('Bearer credential')).toHaveValue('')
  await expect(
    page.getByText('EXECUTION_SUCCEEDED', { exact: true }),
  ).not.toBeVisible()
})
