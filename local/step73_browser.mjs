// Actual isolated dashboard checks. Credentials arrive only over stdin.
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
const require = createRequire(resolve('frontend/package.json'))
const { chromium, expect } = require('@playwright/test')
process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve('frontend/.cache/ms-playwright')
let input = ''
for await (const chunk of process.stdin) input += chunk
const fixture = JSON.parse(input)
if (!/^http:\/\/127\.0\.0\.1:15268$/.test(fixture.base))
  throw Error('Only the isolated fixture frontend is permitted')
const browser = await chromium.launch({ headless: true })
const results = []
try {
  for (const [name, viewport] of [
    ['desktop', { width: 1440, height: 1000 }],
    ['mobile', { width: 390, height: 844 }],
  ]) {
    const context = await browser.newContext({ viewport, isMobile: name === 'mobile' })
    await context.route('**/*', route => {
      if (new URL(route.request().url()).hostname !== '127.0.0.1') return route.abort()
      return route.continue()
    })
    const page = await context.newPage()
    await page.goto(fixture.base + '/banking')
    await page.getByLabel('Operator credential').fill(fixture.token)
    await page.getByRole('button', { name: 'Unlock operator workspace' }).click()
    await page.getByLabel('Account ID', { exact: true }).fill(fixture.account)
    await page.getByRole('button', { name: 'Load account', exact: true }).click()
    await expect(page.getByText(fixture.expectedBalance || '$750.00').first()).toBeVisible({ timeout: 20000 })
    await page.goto(fixture.base + '/monitoring')
    await expect(page.getByRole('button', { name: 'Refresh now', exact: true })).toBeEnabled({ timeout: 20000 })
    await page.getByLabel('Auto refresh').selectOption('0')
    await expect(page.getByText('Process responding', { exact: true })).toBeVisible({ timeout: 20000 })
    for (const route of ['/incidents', '/investigation', '/reconciliation', '/approvals', '/remediation']) {
      const response = await page.goto(fixture.base + route)
      if (response.status() !== 200) throw Error('Dashboard route failed')
      await expect(page.locator('main')).toBeVisible()
    }
    const stored = await page.evaluate(() => Object.values(localStorage).concat(Object.values(sessionStorage)))
    if (stored.some(value => value.includes(fixture.token))) throw Error('Persistent credential found')
    results.push({ project: name, actual_banking_balance: 'passed', monitoring_api: 'passed',
      dashboard_routes: 'passed', credentials_not_persisted: true })
    await context.close()
  }
  process.stdout.write(JSON.stringify({ status: 'PASS', results }) + '\n')
} finally {
  await browser.close()
}
