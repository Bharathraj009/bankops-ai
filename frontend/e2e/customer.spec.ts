import { test, expect } from '@playwright/test'
test.use({ trace: 'off', video: 'off' })
const id = '11111111-1111-4111-8111-111111111111',
  other = '22222222-2222-4222-8222-222222222222'
test('customer login, private history, confirmed retry and role separation', async ({
  page,
}, info) => {
  const token = 'cus_' + 'b'.repeat(43),
    keys: string[] = [],
    bodies: string[] = []
  let writes = 0
  await page.route('**/customer-api/**', async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname.replace('/customer-api', '')
    const account = {
      id,
      accountNumber: 'SYNTHETIC-CUSTOMER-ONLY',
      currency: 'USD',
      balance: writes > 1 ? 750 : 1000,
      createdAt: '2026-01-01T00:00:00Z',
    }
    if (path === '/login') {
      expect(req.headers().authorization).toBeUndefined()
      return route.fulfill({
        json: { token, expiresAt: new Date(Date.now() + 900000).toISOString() },
      })
    }
    expect(req.headers().authorization).toBe('Bearer ' + token)
    if (path === '/me')
      return route.fulfill({
        json: { id: other, username: 'synthetic_customer' },
      })
    if (path === '/logout') return route.fulfill({ status: 204 })
    if (path === '/accounts')
      return route.fulfill({
        json: {
          accounts: [account],
          page: 0,
          size: 10,
          totalElements: 1,
          totalPages: 1,
        },
      })
    if (path.endsWith('/transactions'))
      return route.fulfill({
        json: {
          transactions: [
            {
              transferId: other,
              timestamp: '2026-01-01T00:00:00Z',
              direction: 'INCOMING',
              amount: 10,
              currency: 'USD',
              status: 'COMPLETED',
            },
          ],
          page: 0,
          size: 10,
          totalElements: 1,
          totalPages: 1,
        },
      })
    if (path === '/accounts/' + id) return route.fulfill({ json: account })
    if (path === '/transfers') {
      writes++
      keys.push(req.headers()['idempotency-key'])
      bodies.push(req.postData()!)
      if (writes === 1)
        return route.fulfill({ status: 503, json: { error: 'Unavailable' } })
      return route.fulfill({
        status: 201,
        json: {
          id: other,
          sourceAccountId: id,
          amount: 250,
          currency: 'USD',
          status: 'COMPLETED',
          createdAt: '2026-01-01T00:00:00Z',
        },
      })
    }
    return route.fulfill({ status: 404 })
  })
  await page.goto('/customer')
  await page.getByLabel('Username', { exact: true }).fill('synthetic_customer')
  await page
    .getByLabel('Password', { exact: true })
    .fill('synthetic-password-for-mocked-test')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('button', { name: /SYNTHETIC-CUSTOMER-ONLY/ }).click()
  await expect(page.getByText('INCOMING', { exact: true })).toBeVisible()
  await page.getByLabel('Recipient account ID').fill(other)
  await page.getByLabel('Amount (USD)').fill('250.00')
  await page.getByRole('button', { name: 'Review customer transfer' }).click()
  expect(writes).toBe(0)
  await page
    .getByRole('button', { name: 'Confirm transfer', exact: true })
    .click()
  await expect(page.getByRole('alert')).toBeVisible()
  expect(writes).toBe(1)
  await page.getByRole('button', { name: 'Retry original request' }).click()
  await page
    .getByRole('button', { name: 'Confirm transfer', exact: true })
    .click()
  await expect(page.getByText('Transfer status: COMPLETED.')).toBeVisible()
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBe(keys[1])
  expect(bodies[0]).toBe(bodies[1])
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).some((k) =>
        /token|password|credential/i.test(k),
      ),
    ),
  ).toBe(false)
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: `test-results/customer-${info.project.name}.png`,
    fullPage: true,
  })
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await page.getByRole('button', { name: 'Sign out and clear' }).click()
  await expect(
    page.getByRole('button', { name: 'Sign in', exact: true }),
  ).toBeVisible()
  await page.goto('/banking')
  await expect(page.getByLabel('Operator credential')).toBeVisible()
  await expect(page.getByLabel('Account ID', { exact: true })).toHaveCount(0)
})
