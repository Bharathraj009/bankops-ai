import { test, expect } from '@playwright/test'
import { airflowFixture } from '../src/test/airflowFixture'
test('reconciliation filters and details remain read-only and responsive', async ({
  page,
}, info) => {
  const methods: string[] = []
  await page.route('**/reconciliation-api/incidents/detect', (route) => {
    methods.push(route.request().method())
    return route.fulfill({ json: airflowFixture() })
  })
  await page.goto('/reconciliation')
  await expect(page.getByText('Observed DAG runs')).toBeVisible()
  await expect(page.getByText('Responding', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /Review run/ }).click()
  await expect(page.getByRole('dialog')).toContainText('Read-only connectivity')
  await expect(page.getByRole('dialog')).toContainText(
    'Execution duration unavailable',
  )
  await page.keyboard.press('Escape')
  await page.getByLabel('Result filter').selectOption('task_failure')
  await expect(page.getByText('No runs match this filter')).toBeVisible()
  await page.getByRole('button', { name: 'Clear filter' }).click()
  const beforeRefresh = methods.length
  await page.getByRole('button', { name: 'Refresh evidence' }).click()
  await expect(
    page.getByRole('button', { name: 'Refresh evidence' }),
  ).toBeEnabled()
  expect(methods.length).toBe(beforeRefresh + 1)
  expect(methods.every((method) => method === 'GET')).toBe(true)
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await page.evaluate(() => {
    window.scrollTo(0, 0)
    document.querySelector('.recon-runs .bank-table-wrap')?.scrollTo(0, 0)
  })
  await page.screenshot({
    path: `test-results/reconciliation-${info.project.name}.png`,
    fullPage: true,
  })
})
test('stale and unavailable evidence never establish PASS', async ({
  page,
}) => {
  const d = airflowFixture()
  d.airflow.collected_at = new Date(Date.now() - 120000).toISOString()
  await page.route('**/reconciliation-api/incidents/detect', (route) =>
    route.fulfill({ json: d }),
  )
  await page.goto('/reconciliation')
  await expect(page.getByText(/Stale evidence —/)).toBeVisible()
  await expect(
    page
      .getByRole('region', { name: 'Reconciliation overview' })
      .getByText('INSUFFICIENT_DATA', { exact: true }),
  ).toBeVisible()
  await page.unroute('**/reconciliation-api/incidents/detect')
  await page.route('**/reconciliation-api/incidents/detect', (route) =>
    route.fulfill({ status: 503, body: 'private upstream details' }),
  )
  await page.getByRole('button', { name: 'Refresh evidence' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('body')).not.toContainText(
    'private upstream details',
  )
})
