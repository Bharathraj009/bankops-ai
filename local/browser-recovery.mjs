// Persistent Chromium worker. Credentials stay on stdin/in memory; no screenshots/traces.
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { createInterface } from 'node:readline'
const require = createRequire(resolve('frontend/package.json'))
const { chromium, expect: playwrightExpect } = require('@playwright/test')
const expect = playwrightExpect.configure({ timeout: 15000 })
process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve('frontend/.cache/ms-playwright')
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext()
const banking = await context.newPage()
const monitoring = await context.newPage()
let account
let base
let token = ''
const commands = {
  async init(v) {
    base = v.base
    token = v.token
    account = v.account
    await banking.goto(base + '/banking')
    await banking.getByLabel('Operator credential').fill(v.token)
    await banking.getByRole('button', { name: 'Unlock operator workspace' }).click()
    await banking.getByLabel('Account ID', { exact: true }).fill(account)
    // Delay a real request, then allow it to reach the actual banking service.
    let release
    const gate = new Promise(r => { release = r })
    await banking.route('**/api/v1/accounts/' + account, async route => {
      await gate
      await route.continue()
    })
    await banking.getByRole('button', { name: 'Load account', exact: true }).click()
    await expect(banking.getByText('Loading account and history…')).toBeVisible()
    release()
    await expect(banking.getByText('$750.00').first()).toBeVisible()
    await banking.unroute('**/api/v1/accounts/' + account)
    await monitoring.goto(base + '/monitoring')
    await expect(monitoring.getByRole('button', { name: 'Refresh now', exact: true })).toBeEnabled()
    await monitoring.getByLabel('Auto refresh').selectOption('0')
  },
  async banking_down() {
    const response = banking.waitForResponse(r => r.url().endsWith('/api/v1/accounts/' + account) && r.request().method() === 'GET')
    await banking.getByRole('button', { name: 'Load account', exact: true }).click()
    expect((await response).status()).toBeGreaterThanOrEqual(500)
    await expect(banking.getByRole('alert').first()).toBeVisible({ timeout: 15000 })
  },
  async banking_up() {
    const response = banking.waitForResponse(r => r.url().endsWith('/api/v1/accounts/' + account) && r.request().method() === 'GET')
    await banking.getByRole('button', { name: 'Load account', exact: true }).click()
    expect((await response).status()).toBe(200)
    await expect(banking.getByText('Loading account and history…')).toHaveCount(0)
    await expect(banking.getByText('$750.00').first()).toBeVisible()
    await expect(banking.getByRole('alert')).toHaveCount(0)
  },
  async monitoring_down() {
    const response = monitoring.waitForResponse(r => r.url().endsWith('/monitoring-api/incidents/detect'))
    await monitoring.getByRole('button', { name: 'Refresh now', exact: true }).click()
    await response
    await expect(monitoring.locator('.monitor-state')).toHaveText('Unavailable', { timeout: 20000 })
  },
  async monitoring_up() {
    const response = monitoring.waitForResponse(r => r.url().endsWith('/monitoring-api/incidents/detect'))
    await monitoring.getByRole('button', { name: 'Refresh now', exact: true }).click()
    expect((await response).status()).toBe(200)
    await expect(monitoring.getByRole('button', { name: 'Refresh now', exact: true })).toBeEnabled({ timeout: 20000 })
    await expect(monitoring.getByText('Process responding', { exact: true })).toBeVisible()
    await expect(monitoring.getByRole('alert')).toHaveCount(0)
  },
  async close() { await browser.close() },
}
for await (const line of createInterface({ input: process.stdin })) {
  try {
    const { command, ...values } = JSON.parse(line)
    await commands[command](values)
    process.stdout.write(JSON.stringify({ ok: true, command }) + '\n')
    if (command === 'close') {
      process.stdin.destroy()
      break
    }
  } catch (error) {
    // Keep credentials out of diagnostics while retaining useful assertion context.
    const detail = String(error.message)
    process.stderr.write((token ? detail.replaceAll(token, '[REDACTED]') : detail) + '\n')
    process.stdout.write(JSON.stringify({ ok: false, message: 'Chromium recovery assertion failed' }) + '\n')
  }
}
