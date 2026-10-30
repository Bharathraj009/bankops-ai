// Real Chromium -> Vite security proxy -> real FastAPI/LangGraph; no route mocks.
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
const require = createRequire(resolve('frontend/package.json'))
process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve('frontend/.cache/ms-playwright')
const { chromium, expect } = require('@playwright/test')
let input = ''
for await (const chunk of process.stdin) input += chunk
const config = JSON.parse(input)
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(config.base)) throw Error('Loopback only')
const browser = await chromium.launch({ headless: true })
const results = []
try {
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    const context = await browser.newContext({ viewport })
    await context.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
    const page = await context.newPage()
    const errors = [], posts = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()) })
    await page.goto(config.base + '/investigation')
    await page.getByRole('button', { name: 'Collect evidence', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Investigation evidence', exact: true })).toBeVisible()
    expect(posts).toHaveLength(0)
    await page.getByRole('button', { name: 'Run AI RCA', exact: true }).click()
    const pending = page.waitForResponse(r => r.url().endsWith('/workflows/investigate'))
    await page.getByRole('button', { name: 'Confirm AI investigation', exact: true }).click()
    const response = await pending
    expect(response.status()).toBe(200)
    const report = await response.json()
    expect(report.detection.state).toBe('incident')
    expect(report.rca.retrieval.status).toBe('matched')
    expect(report.rca.root_cause_confirmed).toBe(false)
    if (config.cloud) {
      expect(report.rca.status).toBe('hypotheses')
      await expect(page.getByText('Reported confidence: low')).toBeVisible()
      const ids = new Set(report.rca.retrieval.sources.map(s => s.id))
      for (const h of report.rca.hypotheses) for (const id of h.retrieved_sources) expect(ids.has(id)).toBe(true)
    } else {
      expect(report.rca.reason).toBe('disabled')
      await expect(page.getByText(/LLM inference is disabled on the backend/)).toBeVisible()
    }
    expect(posts).toHaveLength(1)
    expect(errors).toEqual([])
    const request = context.request
    expect((await request.post(config.base + '/investigation-api/remediation/proposals')).status()).toBe(404)
    expect((await request.post(config.base + '/investigation-api/workflows/investigate', { headers: { Origin: 'https://untrusted.invalid' } })).status()).toBe(403)
    results.push({ viewport: name, report, browser_errors: errors.length, workflow_posts: posts.length })
    await context.close()
  }
  process.stdout.write(JSON.stringify(results))
} finally { await browser.close() }
