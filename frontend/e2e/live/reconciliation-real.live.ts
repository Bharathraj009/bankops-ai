import { test, expect } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import {
  parseAirflow,
  assessment,
  taskLabels,
  checkLabels,
} from '../../src/reconciliation'

test('real Airflow PASS, task details, filters, refresh and natural stale expiry', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.BANKOPS_REAL_AIRFLOW !== 'available',
    'Explicit real local Airflow opt-in required',
  )
  test.setTimeout(120000)
  const response = await request.get('/reconciliation-api/incidents/detect')
  expect(response.status()).toBe(200)
  const evidence = parseAirflow(await response.json())!
  expect(evidence.status).toBe('ok')
  expect(evidence.truncated).toBe(false)
  expect(assessment(evidence, Date.now())).toBe('PASS')
  expect(evidence.runs).toHaveLength(1)
  const run = evidence.runs[0]
  expect(run.summary_status).toBe('PASS')
  expect(run.tasks).toHaveLength(4)
  expect(run.tasks.every((t) => t.state === 'success')).toBe(true)
  expect(run.checks).toHaveLength(4)
  expect(run.checks.every((c) => c.violations === 0)).toBe(true)
  const network: {
    url: string
    method: string
    headers: Record<string, string>
  }[] = []
  page.on('request', (r) =>
    network.push({ url: r.url(), method: r.method(), headers: r.headers() }),
  )
  await page.goto('/reconciliation')
  const overview = page.getByRole('region', { name: 'Reconciliation overview' })
  await expect(overview.getByText('PASS', { exact: true })).toBeVisible()
  await expect(overview.getByText('Responding', { exact: true })).toBeVisible()
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await page.getByRole('button', { name: /Review run/ }).click()
  const details = page.getByRole('dialog')
  for (const label of Object.values(taskLabels))
    await expect(details.getByText(label, { exact: true })).toBeVisible()
  for (const label of Object.values(checkLabels))
    await expect(details.getByText(label, { exact: true })).toBeVisible()
  await expect(details.getByText('0 violations', { exact: true })).toHaveCount(
    4,
  )
  await expect(details).toContainText('Execution duration unavailable')
  await page.keyboard.press('Escape')
  for (const filter of [
    'financial_violations',
    'insufficient_data',
    'task_failure',
    'in_progress',
  ]) {
    await page.getByLabel('Result filter').selectOption(filter)
    await expect(page.getByText('No runs match this filter')).toBeVisible()
  }
  await page.getByLabel('Result filter').selectOption('pass')
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await page.getByLabel('Result filter').selectOption('all')
  // Wait for the actual 60-second collection TTL; no mocked payload or clock.
  const before = network.filter((r) =>
    r.url.endsWith('/reconciliation-api/incidents/detect'),
  ).length
  await expect(page.getByText(/Stale evidence —/)).toBeVisible({
    timeout: 70000,
  })
  await expect(
    overview.getByText('INSUFFICIENT_DATA', { exact: true }),
  ).toBeVisible()
  await expect(overview.getByText('Stale', { exact: true })).toBeVisible()
  expect(
    network.filter((r) =>
      r.url.endsWith('/reconciliation-api/incidents/detect'),
    ),
  ).toHaveLength(before)
  const freshResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith('/reconciliation-api/incidents/detect') &&
      r.status() === 200,
  )
  await page.getByRole('button', { name: 'Refresh evidence' }).click()
  const refreshed = parseAirflow(await (await freshResponse).json())!
  expect(Date.parse(refreshed.collected_at)).toBeGreaterThan(
    Date.parse(evidence.collected_at),
  )
  await expect(overview.getByText('PASS', { exact: true })).toBeVisible()
  await expect(page.getByText(/Stale evidence —/)).toHaveCount(0)
  expect(
    network.every(
      (r) =>
        r.url.startsWith('http://127.0.0.1:5179/') &&
        r.method === 'GET' &&
        !r.headers.authorization,
    ),
  ).toBe(true)
  await mkdir('.cache/step62-live', { recursive: true })
  await writeFile(
    '.cache/step62-live/real-evidence.json',
    JSON.stringify({ initial: evidence, refreshed }, null, 2),
  )
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: '.cache/step62-live/real-dashboard.png',
    fullPage: true,
  })
})

test('real agent returns unavailable Airflow without false PASS', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.BANKOPS_REAL_AIRFLOW !== 'unavailable',
    'Requires closed-loopback source configuration',
  )
  const response = await request.get('/reconciliation-api/incidents/detect')
  expect(response.status()).toBe(200)
  const evidence = parseAirflow(await response.json())!
  expect(evidence.status).toBe('unavailable')
  expect(evidence.runs).toHaveLength(0)
  await page.goto('/reconciliation')
  const overview = page.getByRole('region', { name: 'Reconciliation overview' })
  await expect(
    overview.getByText('INSUFFICIENT_DATA', { exact: true }),
  ).toBeVisible()
  await expect(overview.getByText('unavailable', { exact: true })).toBeVisible()
  await expect(page.getByText('No run evidence available')).toBeVisible()
  await expect(overview.getByText('PASS', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Refresh evidence' }).click()
  await expect(
    page.getByRole('button', { name: 'Refresh evidence' }),
  ).toBeEnabled()
  await expect(
    overview.getByText('INSUFFICIENT_DATA', { exact: true }),
  ).toBeVisible()
})
