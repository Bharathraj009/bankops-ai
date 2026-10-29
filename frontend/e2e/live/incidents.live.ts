import { test, expect } from '@playwright/test'
test('isolated synthetic agent and real LangGraph integration', async ({
  page,
  request,
}) => {
  if (process.env.BANKOPS_SYNTHETIC_INCIDENTS !== 'step60-local-only')
    throw new Error('Explicit synthetic environment opt-in required')
  // Fixture fingerprint check before the only POST; never point this test at a live provider.
  const initial = await request.get('/investigation-api/incidents/investigate')
  expect(initial.status()).toBe(200)
  const fixture = await initial.json()
  expect(fixture.traces.traces[0].trace_id).toBe('a'.repeat(32))
  expect(fixture.logs.events[0].correlation_id).toBe(
    '11111111-1111-4111-8111-111111111111',
  )
  const errors: string[] = []
  const calls: { url: string; method: string }[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('request', (r) => {
    if (r.url().includes('-api/') || r.url().includes('/api/v1'))
      calls.push({ url: r.url(), method: r.method() })
  })
  await page.goto('/incidents')
  await expect(page.getByRole('button', { name: /^HTTP errors/ })).toBeVisible()
  await page.getByRole('button', { name: /^HTTP errors/ }).click()
  await page.getByRole('link', { name: 'Investigate this rule' }).click()
  await page.getByRole('button', { name: 'Collect evidence' }).click()
  await expect(
    page.getByRole('heading', { name: 'Investigation evidence' }),
  ).toBeVisible()
  await expect(page.getByText(/Not requested. Observed evidence/)).toBeVisible()
  expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  await page.getByRole('button', { name: 'Run AI RCA' }).click()
  const result = page.waitForResponse((r) =>
    r.url().endsWith('/workflows/investigate'),
  )
  await page.getByRole('button', { name: 'Confirm AI investigation' }).click()
  const response = await result
  expect(response.status()).toBe(200)
  const report = await response.json()
  expect(report.detection.state).toBe('incident')
  expect(report.rca.root_cause_confirmed).toBe(false)
  if (process.env.BANKOPS_SYNTHETIC_RCA === 'fixture') {
    expect(report.rca.status).toBe('hypotheses')
    await expect(page.getByText('Reported confidence: low')).toBeVisible()
    expect(report.rca.hypotheses[0].supporting_evidence).toEqual([
      'rule.high_http_error_rate',
    ])
  } else {
    expect(report.rca.reason).toBe('disabled')
    await expect(
      page.getByText(/LLM inference is disabled on the backend/),
    ).toBeVisible()
  }
  await expect(page.getByText('Causality is unconfirmed')).toBeVisible()
  await expect(
    page.getByText('HTTP request completed', { exact: true }),
  ).toBeVisible()
  expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1)
  expect(calls.every((c) => c.url.includes('/investigation-api/'))).toBe(true)
  expect(errors).toEqual([])
  expect((await request.post('/investigation-api/approvals')).status()).toBe(
    404,
  )
  expect(
    (await request.get('/investigation-api/workflows/investigate')).status(),
  ).toBe(404)
  expect(
    (
      await request.get('/investigation-api/incidents/detect?provider=enable')
    ).status(),
  ).toBe(404)
  await page.screenshot({
    path: `test-results/incidents-isolated-${process.env.BANKOPS_SYNTHETIC_RCA === 'fixture' ? 'fixture' : 'disabled'}.png`,
    fullPage: true,
  })
})
