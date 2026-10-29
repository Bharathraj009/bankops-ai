import { test, expect } from '@playwright/test'
import { incidentFixture, reportFixture } from '../src/test/incidentFixture'
test('incident evidence and explicitly confirmed AI workflow', async ({
  page,
}, info) => {
  let posts = 0
  let unavailable = false
  const requests: string[] = []
  await page.route('**/investigation-api/**', async (route) => {
    const r = route.request()
    requests.push(r.url())
    if (unavailable) {
      await route.fulfill({ status: 503, body: 'private URL' })
      return
    }
    if (r.method() === 'POST') posts++
    await route.fulfill({
      json: r.url().endsWith('/detect') ? incidentFixture() : reportFixture(),
    })
  })
  await page.goto('/incidents')
  await expect(page.getByRole('button', { name: /^HTTP errors/ })).toBeVisible()
  await expect(page.getByText('Not provided by API')).toBeVisible()
  expect(posts).toBe(0)
  await page.getByRole('button', { name: /^HTTP errors/ }).click()
  await expect(
    page.getByRole('heading', { name: /HTTP errors.*observed details/ }),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Investigate this rule' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'AI Investigation',
  )
  await page.getByRole('button', { name: 'Collect evidence' }).click()
  await expect(
    page.getByRole('heading', { name: 'Investigation evidence' }),
  ).toBeVisible()
  await expect(page.getByText(/Not requested. Observed evidence/)).toBeVisible()
  expect(posts).toBe(0)
  await page.getByRole('button', { name: 'Run AI RCA' }).click()
  await page.getByRole('button', { name: 'Confirm AI investigation' }).click()
  await expect(page.getByText('Reported confidence: low')).toBeVisible()
  expect(posts).toBe(1)
  await expect(page.getByText('Causality is unconfirmed')).toBeVisible()
  await page.getByText(/Trace 1 ·/).click()
  await expect(page.getByRole('cell', { name: 'db.call' })).toBeVisible()
  await expect(
    page.getByText('HTTP request completed', { exact: true }),
  ).toBeVisible()
  await page.screenshot({
    path: `test-results/incidents-${info.project.name}.png`,
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  unavailable = true
  await page.getByRole('button', { name: 'Refresh detection' }).click()
  await expect(page.getByRole('alert')).toContainText(
    'Detection service unavailable',
  )
  expect(posts).toBe(1)
  expect(
    requests.every(
      (u) => !u.includes('approvals') && !u.includes('remediation'),
    ),
  ).toBe(true)
})
