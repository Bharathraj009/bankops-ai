import { test, expect } from '@playwright/test'
test.use({ trace: 'off', video: 'off' })
test('real isolated banking workflow', async ({ page, request }) => {
  if (process.env.BANKOPS_ISOLATED_BANKING !== 'step58-local-only')
    throw new Error('Explicit isolated test environment required')
  const id = process.env.BANKOPS_ISOLATED_SOURCE_ID!
  if (!id) throw new Error('A unique isolated source fixture is required')
  // Confirm the unique fixture before any write; a misdirected proxy must fail closed.
  const operator = process.env.BANKOPS_ISOLATED_OPERATOR_TOKEN
  expect(
    operator,
    'Provide the isolated backend operator credential',
  ).toBeTruthy()
  const fixture = await request.get(`/api/v1/accounts/${id}`, {
    headers: { Authorization: `Bearer ${operator}` },
  })
  expect(fixture.status()).toBe(200)
  const source = await fixture.json()
  expect(source.accountNumber).toBe(`STEP58-SOURCE-${id}`)
  expect(source.balance).toBe(1000)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto('/banking')
  await page.getByLabel('Operator credential').fill(operator!)
  await page.getByRole('button', { name: 'Unlock operator workspace' }).click()
  await page
    .getByRole('button', { name: 'Create account', exact: true })
    .click()
  await page
    .getByLabel('Account number', { exact: true })
    .fill(`STEP58-${crypto.randomUUID()}`)
  const created = page.waitForResponse(
    (r) =>
      r.url().endsWith('/api/v1/accounts') && r.request().method() === 'POST',
  )
  await page
    .getByRole('button', { name: 'Create zero-balance account' })
    .click()
  const createdResponse = await created
  expect(createdResponse.status()).toBe(201)
  const account = await createdResponse.json()
  expect(account.balance).toBe(0)
  await expect(
    page.getByText('Account created with zero opening balance.'),
  ).toBeVisible()
  await page.getByLabel('Account ID', { exact: true }).fill(id)
  await page.getByRole('button', { name: 'Load account' }).click()
  await expect(page.getByText('$1,000.00').first()).toBeVisible()
  await page.getByLabel('Destination account ID').fill(account.id)
  await page.getByLabel('Amount (USD)').fill('250.00')
  await page.getByRole('button', { name: 'Review transfer' }).click()
  const completed = page.waitForResponse(
    (r) =>
      r.url().endsWith('/api/v1/transfers') && r.request().method() === 'POST',
  )
  await page
    .getByRole('button', { name: 'Confirm / retry same transfer' })
    .click()
  const res = await completed
  expect(res.status()).toBe(201)
  const transfer = await res.json()
  expect(transfer.status).toBe('COMPLETED')
  await expect(
    page.getByRole('dialog', { name: 'Transfer details' }),
  ).toContainText(transfer.id)
  const replay = await request.post('/api/v1/transfers', {
    headers: { 'Idempotency-Key': res.request().headers()['idempotency-key'] },
    data: JSON.parse(res.request().postData()!),
  })
  expect(replay.status()).toBe(200)
  expect((await replay.json()).id).toBe(transfer.id)
  const conflict = await request.post('/api/v1/transfers', {
    headers: { 'Idempotency-Key': res.request().headers()['idempotency-key'] },
    data: {
      sourceAccountId: id,
      destinationAccountId: account.id,
      amount: 251,
    },
  })
  expect(conflict.status()).toBe(409)
  await page.getByRole('button', { name: 'Close transfer details' }).click()
  await expect(page.getByText('$750.00').first()).toBeVisible()
  await expect(
    page.getByRole('table', { name: 'Completed transaction history' }),
  ).toContainText('OUTGOING')
  await page.getByLabel('Account ID', { exact: true }).fill(account.id)
  await page.getByRole('button', { name: 'Load account' }).click()
  await expect(page.locator('.balance-card .bank-balance')).toHaveText(
    '$250.00',
  )
  await expect(
    page.getByRole('table', { name: 'Completed transaction history' }),
  ).toContainText('INCOMING')
  await page.screenshot({
    path: 'test-results/banking-real-isolated.png',
    fullPage: true,
  })
  expect(errors).toEqual([])
})
