import { test, expect } from '@playwright/test'
import { monitoringFixture } from '../src/test/monitoringFixture'
test('monitoring charts, controls, missing evidence and stale states', async ({
  page,
}, info) => {
  let missing = false
  let failed = false
  const requests: string[] = []
  await page.route('**/monitoring-api/**', async (route) => {
    requests.push(route.request().method())
    if (route.request().url().endsWith('/health')) {
      await route.fulfill({
        json: { status: 'ok', service: 'bankops-reliability-agent' },
      })
      return
    }
    if (failed) {
      await route.fulfill({ status: 503, body: 'private error' })
      return
    }
    const data = monitoringFixture()
    if (missing) {
      data.state = 'insufficient_data'
      data.evidence.metrics.find((m) => m.name === 'api_latency_p95')!.status =
        'missing'
      data.rules[2].state = 'insufficient_data'
      data.rules[2].reason = 'missing_or_invalid_evidence'
    }
    await route.fulfill({ json: data })
  })
  await page.goto('/monitoring')
  await expect(page.getByText('Healthy', { exact: true })).toBeVisible()
  await page.getByLabel('Auto refresh').selectOption('0')
  await page
    .getByLabel('Signal', { exact: true })
    .selectOption('api_latency_p95')
  await page.getByLabel('Local observation range').selectOption('60')
  const point = page.getByRole('button', { name: /200 ms/ })
  await point.focus()
  await expect(page.locator('.chart-tooltip')).toContainText('200 ms')
  missing = true
  await page.getByRole('button', { name: 'Refresh now' }).click()
  await expect(page.locator('.monitor-state')).toHaveText('Insufficient data')
  await expect(
    page.getByText(
      'No valid observations for this metric. Missing values are not plotted.',
    ),
  ).not.toBeVisible()
  await page.screenshot({
    path: `test-results/monitoring-${info.project.name}.png`,
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  failed = true
  await page.getByRole('button', { name: 'Refresh now' }).click()
  await expect(page.locator('.monitor-state')).toHaveText('Unavailable')
  await expect(page.getByText(/Stale or cached/)).toBeVisible()
  await expect(page.getByText('private error')).not.toBeVisible()
  expect(requests.every((method) => method === 'GET')).toBe(true)
})
