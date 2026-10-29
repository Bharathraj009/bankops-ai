import { test, expect } from '@playwright/test'

test('cross-origin API writes are rejected before proxying', async ({
  request,
}) => {
  for (const path of [
    '/api/v1/accounts',
    '/api/v1/transfers',
    '/investigation-api/workflows/investigate',
    '/governance-api/remediation/proposals/11111111-1111-4111-8111-111111111111/approve',
  ]) {
    const response = await request.post(path, {
      headers: { Origin: 'https://attacker.invalid' },
      data: {},
    })
    expect(response.status()).toBe(403)
    expect(response.headers()['cache-control']).toBe('no-store')
    expect(response.headers()['access-control-allow-origin']).toBeUndefined()
  }
})
test('frontend proxy exposes only supported banking operations', async ({
  request,
  page,
}) => {
  for (const path of [
    '/api/v1/dev/accounts/11111111-1111-4111-8111-111111111111/fund',
    '/api/v1/unknown',
  ])
    expect((await request.post(path, { data: {} })).status()).toBe(404)
  expect(
    (
      await request.delete(
        '/api/v1/accounts/11111111-1111-4111-8111-111111111111',
      )
    ).status(),
  ).toBe(404)
  await page.goto('/')
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).filter((k) =>
        /token|credential|password/i.test(k),
      ),
    ),
  ).toEqual([])
})
