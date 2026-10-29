import { test, expect } from '@playwright/test'
import {
  definitions,
  formatMetric,
  health,
  observed,
  parseSnapshot,
} from '../../src/monitoring'
test('real local monitoring read-only integration', async ({
  page,
  request,
}) => {
  if (process.env.BANKOPS_LIVE_MONITORING !== 'read-only-local')
    throw new Error('Explicit live monitoring opt-in required')
  const calls: { url: string; method: string }[] = []
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('request', (r) => {
    if (r.url().includes('/monitoring-api/') || r.url().includes('/api/v1/'))
      calls.push({ url: r.url(), method: r.method() })
  })
  const detection = page.waitForResponse((r) =>
    r.url().endsWith('/monitoring-api/incidents/detect'),
  )
  await page.goto('/monitoring')
  const response = await detection
  expect(response.status()).toBe(200)
  const s = parseSnapshot(await response.json())
  await expect(page.locator('.monitor-state')).toHaveText(
    health(s, Date.now(), false),
  )
  await expect(page.getByText('Process responding')).toBeVisible()
  for (const name of Object.keys(definitions).filter(
    (n) => n !== 'banking_availability',
  ) as (keyof typeof definitions)[]) {
    const card = page.getByRole('region', { name: definitions[name].label })
    await expect(card.locator('strong')).toContainText(
      formatMetric(name, observed(s, name, Date.now())),
    )
  }
  await page.getByLabel('Auto refresh').selectOption('0')
  const next = page.waitForResponse((r) =>
    r.url().endsWith('/monitoring-api/incidents/detect'),
  )
  await page.getByRole('button', { name: 'Refresh now' }).click()
  expect((await next).status()).toBe(200)
  await page.getByText('Recent observation values', { exact: true }).click()
  await expect(page.getByRole('row')).toHaveCount(3)
  const html = await page.locator('main').innerText()
  expect(html).not.toMatch(/https?:\/\/|password|api[_-]?key/i)
  expect(
    (await request.post('/monitoring-api/incidents/detect')).status(),
  ).toBe(404)
  expect((await request.get('/monitoring-api/approvals')).status()).toBe(404)
  expect(
    (
      await request.get('/monitoring-api/incidents/detect?url=http://private')
    ).status(),
  ).toBe(404)
  expect(
    calls.every(
      (c) => c.method === 'GET' && c.url.includes('/monitoring-api/'),
    ),
  ).toBe(true)
  expect(errors).toEqual([])
  await page.screenshot({
    path: 'test-results/monitoring-real.png',
    fullPage: true,
  })
})
