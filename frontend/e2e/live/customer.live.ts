import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
test('isolated customer registration, ownership, real transfer and operator separation', async ({
  page,
  request,
}) => {
  const security = process.env.BANKOPS_SECURITY_E2E === 'step66-isolated'
  test.skip(
    !security && process.env.BANKOPS_ISOLATED_CUSTOMER !== 'step64-local-only',
    'Requires explicitly isolated fixture',
  )
  test.setTimeout(60000)
  const fixture = JSON.parse(
    security
      ? process.env.BANKOPS_SECURITY_SESSION!
      : await readFile('.cache/step64/session.json', 'utf8'),
  )
  const alice = 'alice_' + randomUUID().replaceAll('-', ''),
    bob = 'bob_' + randomUUID().replaceAll('-', ''),
    password = 'Test-' + randomUUID()
  await page.goto('/customer')
  await page.getByRole('button', { name: 'Create customer login' }).click()
  await page.getByLabel('Username', { exact: true }).fill(alice)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Register customer' }).click()
  await expect(
    page.getByText('Registration complete. Sign in with your new credentials.'),
  ).toBeVisible()
  await page.getByLabel('Username', { exact: true }).fill(alice)
  await page.getByLabel('Password', { exact: true }).fill(password)
  const login = page.waitForResponse(
    (r) => r.url().endsWith('/customer-api/login') && r.status() === 200,
  )
  const authenticated = page.waitForRequest(
    (r) => r.url().includes('/customer-api/accounts?') && r.method() === 'GET',
  )
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  expect((await login).status()).toBe(200)
  const token = (await authenticated).headers()['authorization'].slice(7)
  await expect(page.getByText(`Customer · ${alice}`)).toBeVisible()
  const created = page.waitForResponse(
    (r) =>
      r.url().endsWith('/customer-api/accounts') &&
      r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Open USD account' }).click()
  expect((await created).status()).toBe(201)
  await expect(
    page.getByText('Account opened with a zero balance.'),
  ).toBeVisible()
  const owned = await request.get('/customer-api/accounts?page=0&size=10', {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(owned.status()).toBe(200)
  const account = (await owned.json()).accounts[0]
  expect(account.balance).toBe(0)
  const register = await request.post('/customer-api/register', {
    data: { username: bob, password },
  })
  expect(register.status()).toBe(201)
  const loginBob = await request.post('/customer-api/login', {
    data: { username: bob, password },
  })
  expect(loginBob.status()).toBe(200)
  const bobToken = (await loginBob.json()).token,
    bobHeaders = { Authorization: `Bearer ${bobToken}` },
    aliceHeaders = { Authorization: `Bearer ${token}` }
  const bobCreated = await request.post('/customer-api/accounts', {
    headers: bobHeaders,
    data: {},
  })
  expect(bobCreated.status()).toBe(201)
  const recipient = await bobCreated.json()
  // Synthetic reserve and all accounts are in this fixture's unique isolated schema.
  const fund = await request.post(
    `http://127.0.0.1:${security ? 18066 : 18064}/api/v1/dev/accounts/${account.id}/fund`,
    {
      headers: {
        Authorization: `Bearer ${fixture.operator}`,
        'Idempotency-Key': randomUUID(),
      },
      data: { amount: 1000 },
    },
  )
  expect(fund.status()).toBe(201)
  await page.getByRole('button', { name: 'Refresh my accounts' }).click()
  await expect(page.getByText('$1,000.00').first()).toBeVisible()
  await page.getByLabel('Recipient account ID').fill(recipient.id)
  await page.getByLabel('Amount (USD)').fill('250.00')
  await page.getByRole('button', { name: 'Review customer transfer' }).click()
  const transfer = page.waitForResponse(
    (r) =>
      r.url().endsWith('/customer-api/transfers') &&
      r.request().method() === 'POST',
  )
  await page
    .getByRole('button', { name: 'Confirm transfer', exact: true })
    .click()
  const response = await transfer
  expect(response.status()).toBe(201)
  await expect(page.getByText('Transfer status: COMPLETED.')).toBeVisible()
  await expect(page.getByText('$750.00').first()).toBeVisible()
  const original = response.request(),
    retry = await request.post('/customer-api/transfers', {
      headers: {
        ...aliceHeaders,
        'Idempotency-Key': original.headers()['idempotency-key'],
      },
      data: JSON.parse(original.postData()!),
    })
  expect(retry.status()).toBe(200)
  const result = await retry.json()
  expect(result.destinationAccountId).toBeUndefined()
  expect(JSON.stringify(result)).not.toContain(recipient.id)
  const readBack = await request.get('/customer-api/transfers/' + result.id, {
    headers: aliceHeaders,
  })
  expect(readBack.status()).toBe(200)
  expect(await readBack.json()).toEqual(result)
  expect(
    (
      await request.get('/customer-api/accounts/' + recipient.id, {
        headers: aliceHeaders,
      })
    ).status(),
  ).toBe(404)
  expect(
    (
      await request.post('/customer-api/transfers', {
        headers: { ...bobHeaders, 'Idempotency-Key': randomUUID() },
        data: {
          sourceAccountId: account.id,
          destinationAccountId: recipient.id,
          amount: 1,
        },
      })
    ).status(),
  ).toBe(404)
  const bobAccount = await (
    await request.get('/customer-api/accounts/' + recipient.id, {
      headers: bobHeaders,
    })
  ).json()
  expect(bobAccount.balance).toBe(250)
  const bobHistory = await (
    await request.get(`/customer-api/accounts/${recipient.id}/transactions`, {
      headers: bobHeaders,
    })
  ).json()
  expect(bobHistory.transactions[0].direction).toBe('INCOMING')
  expect(Object.keys(bobHistory.transactions[0])).toHaveLength(6)
  expect(
    (
      await request.get('/customer-api/transfers/' + result.id, {
        headers: bobHeaders,
      })
    ).status(),
  ).toBe(404)
  expect((await request.get('/api/v1/operator/me')).status()).toBe(401)
  expect(
    (
      await request.get('/api/v1/accounts/' + account.id, {
        headers: aliceHeaders,
      })
    ).status(),
  ).toBe(401)
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).some((k) =>
        /token|password|credential/i.test(k),
      ),
    ),
  ).toBe(false)
  await page.evaluate(() => window.scrollTo(0, 0))
  if (!security)
    await page.screenshot({
      path: '.cache/step64/customer-real.png',
      fullPage: true,
    })
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await page.getByRole('button', { name: 'Sign out and clear' }).click()
  await expect(
    page.getByRole('button', { name: 'Sign in', exact: true }),
  ).toBeVisible()
  expect(
    (await request.get('/customer-api/me', { headers: aliceHeaders })).status(),
  ).toBe(401)
  await page.goto('/banking')
  await expect(page.getByLabel('Operator credential')).toBeVisible()
  await page.getByLabel('Operator credential').fill(fixture.operator)
  await page.getByRole('button', { name: 'Unlock operator workspace' }).click()
  await expect(page.getByLabel('Account ID', { exact: true })).toBeVisible()
  if (security) {
    const logs = await readFile(
      process.env.BANKOPS_SECURITY_LOG_DIR! + '/banking-service.log',
      'utf8',
    )
    for (const secret of [
      token,
      bobToken,
      password,
      alice,
      bob,
      account.id,
      recipient.id,
      result.id,
      account.accountNumber,
      recipient.accountNumber,
      original.headers()['idempotency-key'],
    ])
      expect(logs.includes(secret)).toBe(false)
    expect(
      /"(?:balance|amount|accountNumber|idempotencyKey)"\s*:/.test(logs),
    ).toBe(false)
  }
})
