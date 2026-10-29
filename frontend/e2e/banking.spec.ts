import { test, expect } from '@playwright/test'
const id = '11111111-1111-4111-8111-111111111111'
const destination = '22222222-2222-4222-8222-222222222222'
test('banking account creation, lookup, history pagination and explicit safe transfer retry', async ({
  page,
}, info) => {
  let writes = 0
  const keys: string[] = []
  await page.route('**/api/v1/**', async (route) => {
    if (route.request().url().endsWith('/operator/me')) {
      await route.fulfill({ json: { role: 'OPERATOR' } })
      return
    }
    const req = route.request()
    const url = req.url()
    if (req.method() === 'POST' && url.endsWith('/transfers')) {
      writes++
      keys.push(req.headers()['idempotency-key'])
      if (writes === 1) {
        await route.abort()
        return
      }
      await route.fulfill({
        json: {
          id: destination,
          sourceAccountId: id,
          destinationAccountId: destination,
          amount: 250,
          currency: 'USD',
          status: 'COMPLETED',
          createdAt: '2026-01-01T00:00:00Z',
        },
      })
      return
    }
    if (url.includes('/transactions')) {
      const second = url.includes('page=1')
      await route.fulfill({
        json: {
          transactions: [
            {
              transferId: destination,
              timestamp: second
                ? '2025-01-01T00:00:00Z'
                : '2026-01-01T00:00:00Z',
              direction: second ? 'INCOMING' : 'OUTGOING',
              amount: 250,
              currency: 'USD',
              status: 'COMPLETED',
            },
          ],
          page: second ? 1 : 0,
          size: 10,
          totalElements: 11,
          totalPages: 2,
        },
      })
      return
    }
    await route.fulfill({
      status: req.method() === 'POST' ? 201 : 200,
      json: {
        id,
        accountNumber: 'SYNTHETIC-ONLY',
        currency: 'USD',
        balance: writes > 1 ? 750 : 1000,
        createdAt: '2026-01-01T00:00:00Z',
      },
    })
  })
  await page.goto('/banking')
  await page
    .getByLabel('Operator credential')
    .fill('isolated-operator-browser-regression-only')
  await page.getByRole('button', { name: 'Unlock operator workspace' }).click()
  await page.getByLabel('Account ID', { exact: true }).fill(id)
  await page.getByRole('button', { name: 'Load account' }).click()
  await expect(page.getByText('$1,000.00').first()).toBeVisible()
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByText('Page 2', { exact: false })).toBeVisible()
  await page.getByLabel('Direction (this page)').selectOption('INCOMING')
  await expect(
    page.getByRole('table', { name: 'Completed transaction history' }),
  ).toContainText('INCOMING')
  await page.getByLabel('Destination account ID').fill(destination)
  await page.getByLabel('Amount (USD)').fill('250.00')
  await page.getByRole('button', { name: 'Review transfer' }).click()
  expect(writes).toBe(0)
  await page
    .getByRole('button', { name: 'Confirm / retry same transfer' })
    .click()
  await expect(
    page.getByRole('dialog', { name: 'Confirm transfer' }),
  ).toContainText('unknown outcome')
  expect(writes).toBe(1)
  await page
    .getByRole('button', { name: 'Confirm / retry same transfer' })
    .click()
  await expect(
    page.getByRole('dialog', { name: 'Transfer details' }),
  ).toContainText('COMPLETED')
  expect(writes).toBe(2)
  expect(keys[0]).toBe(keys[1])
  await page.getByRole('button', { name: 'Close transfer details' }).click()
  await expect(page.getByText('$750.00').first()).toBeVisible()
  await page.screenshot({
    path: `test-results/banking-${info.project.name}.png`,
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await page
    .getByRole('button', { name: 'Create account', exact: true })
    .click()
  await page.getByLabel('Account number', { exact: true }).fill('SYNTHETIC-NEW')
  await page
    .getByRole('button', { name: 'Create zero-balance account' })
    .click()
  await expect(
    page.getByText('Account created with zero opening balance.'),
  ).toBeVisible()
})
