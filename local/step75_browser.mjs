import { createRequire } from 'node:module'
import { resolve } from 'node:path'
const require = createRequire(resolve('frontend/package.json'))
process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve('frontend/.cache/ms-playwright')
const { chromium, expect } = require('@playwright/test')
let input = ''
for await (const chunk of process.stdin) input += chunk
const { base } = JSON.parse(input)
if (base !== 'http://127.0.0.1:15268') throw Error('Disposable fixture only')
const browser = await chromium.launch({ headless: true })
const results = []
try {
  for (const [name, viewport] of [['desktop', {width:1440,height:1000}], ['mobile', {width:390,height:844}]]) {
    const context = await browser.newContext({viewport})
    await context.route('**/*', r => new URL(r.request().url()).hostname === '127.0.0.1' ? r.continue() : r.abort())
    const page = await context.newPage(), errors = []
    page.on('pageerror', e => errors.push(e.message))
    await page.goto(base + '/investigation')
    await page.getByRole('button', {name:'Run AI RCA',exact:true}).click()
    const pending = page.waitForResponse(r => r.url().endsWith('/workflows/investigate'))
    await page.getByRole('button', {name:'Confirm AI investigation',exact:true}).click()
    const response = await pending
    expect(response.status()).toBe(200)
    const report = await response.json()
    expect(report.detection.triggered_rules).toContain('reconciliation_insufficient_data')
    expect(report.detection.airflow.runs[0].summary_status).toBe('INSUFFICIENT_DATA')
    expect(report.rca.reason).toBe('disabled')
    const viewer = page.getByRole('region', {name:'Retrieved evidence references'})
    await expect(viewer).toBeVisible()
    const source = report.rca.retrieval.sources.find(s => s.document_id === 'reconciliation')
    expect(source.reviewed).toBe(true)
    await viewer.locator('summary').first().click()
    await expect(viewer.getByText(source.id, {exact:true})).toBeVisible()
    await expect(viewer.getByText('corpus://synthetic/reconciliation', {exact:true}).first()).toBeVisible()
    expect(errors).toEqual([])
    results.push({viewport:name, incident:'reconciliation_insufficient_data', summary:'INSUFFICIENT_DATA',
      cited_source:source.id, native_info_events:report.logs.events.filter(e=>e.level==='INFO').length,
      retrieval:report.rca.retrieval.status, cloud_inference:false, browser_errors:errors.length})
    await context.close()
  }
  process.stdout.write(JSON.stringify(results))
} finally { await browser.close() }
