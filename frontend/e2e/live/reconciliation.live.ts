import { test, expect } from '@playwright/test'
test('real agent collects authenticated synthetic Airflow evidence without writes', async ({
  page,
  request,
}) => {
  test.skip(
    process.env.BANKOPS_SYNTHETIC_RECONCILIATION !== 'step62-local-only',
    'Requires isolated fixture',
  )
  const requests: string[] = []
  page.on('request', (r) => requests.push(r.url()))
  await page.goto('/reconciliation')
  await expect(page.getByText('Responding', { exact: true })).toBeVisible()
  await expect(page.getByText('FAIL', { exact: true })).toBeVisible()
  await expect(page.locator('tbody tr')).toHaveCount(5)
  await page.getByLabel('Result filter').selectOption('financial_violations')
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await page.getByRole('button', { name: /Review run/ }).click()
  await expect(page.getByRole('dialog')).toContainText('1 violations')
  await expect(page.getByRole('dialog')).toContainText('Recorded summary: FAIL')
  await page.keyboard.press('Escape')
  await page.getByLabel('Result filter').selectOption('task_failure')
  await page.getByRole('button', { name: /Review run/ }).click()
  await expect(page.getByRole('dialog')).toContainText('Recorded summary: PASS')
  await expect(
    page.getByRole('dialog').getByText('Task failure', { exact: true }),
  ).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByLabel('Result filter').selectOption('insufficient_data')
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await page.getByLabel('Result filter').selectOption('in_progress')
  await expect(page.locator('tbody tr')).toHaveCount(1)
  const baseline = await (
    await request.get('http://127.0.0.1:18064/fixture-status')
  ).json()
  expect(baseline.authenticated_gets).toBeGreaterThanOrEqual(10)
  await page.getByRole('button', { name: 'Refresh evidence' }).click()
  await expect(
    page.getByRole('button', { name: 'Refresh evidence' }),
  ).toBeEnabled()
  expect(
    requests.every((url) => url.startsWith('http://127.0.0.1:5179/')),
  ).toBe(true)
  const denied = await request.get(
    'http://127.0.0.1:18064/api/v2/dags/bankops_daily_reconciliation/dagRuns',
  )
  expect(denied.status()).toBe(401)
  const counts = await (
    await request.get('http://127.0.0.1:18064/fixture-status')
  ).json()
  // Per collection: listing + five task lists + four completed execution summaries.
  expect(counts.authenticated_gets - baseline.authenticated_gets).toBe(10)
  expect(counts.unauthorized).toBeGreaterThanOrEqual(1)
  expect(counts.writes).toBe(0)
  // Proxy denies financial/state-changing and arbitrary upstream routes.
  for (const path of [
    '/reconciliation-api/dagRuns',
    '/reconciliation-api/incidents/detect?path=secret',
  ])
    expect((await request.get(path)).status()).toBe(404)
  expect(
    (await request.post('/reconciliation-api/incidents/detect')).status(),
  ).toBe(404)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: 'test-results/reconciliation-live/workspace.png',
    fullPage: true,
  })
})
