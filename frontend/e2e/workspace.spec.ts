import { test, expect } from '@playwright/test'

test('renders an honest workspace without browser errors or service requests', async ({
  page,
}, testInfo) => {
  const errors: string[] = []
  const serviceRequests: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('request', (request) => {
    if (
      request.url().includes('/api/') ||
      !request.url().startsWith('http://127.0.0.1:5173')
    )
      serviceRequests.push(request.url())
  })
  await page.goto('/')
  await expect(
    page.getByRole('heading', { name: 'Operations overview' }),
  ).toBeVisible()
  await expect(
    page.getByText('Banking & monitoring connect on demand'),
  ).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'Explore banking' }),
  ).toBeVisible()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await page.screenshot({
    path: `test-results/overview-${testInfo.project.name}.png`,
    fullPage: true,
  })
  expect(errors).toEqual([])
  expect(serviceRequests).toEqual([])
})

test('theme and navigation preferences survive reload', async ({
  page,
}, testInfo) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Switch to dark theme' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.reload()
  await expect(
    page.getByRole('button', { name: 'Switch to light theme' }),
  ).toBeVisible()
  await page.screenshot({
    path: `test-results/dark-${testInfo.project.name}.png`,
    fullPage: true,
  })
  if (testInfo.project.name === 'desktop') {
    await page.getByRole('button', { name: 'Collapse sidebar' }).click()
    await page.reload()
    await expect(
      page.getByRole('button', { name: 'Expand sidebar' }),
    ).toHaveAttribute('aria-expanded', 'false')
    await page
      .getByRole('navigation', { name: 'Main navigation' })
      .getByRole('link', { name: 'Banking', exact: true })
      .click()
  } else {
    const open = page.getByRole('button', { name: 'Open navigation' })
    await open.click()
    await expect(
      page.getByRole('dialog', { name: 'Workspace navigation' }),
    ).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(
      page.getByRole('dialog', { name: 'Workspace navigation' }),
    ).not.toBeVisible()
    await expect(open).toBeFocused()
    await open.click()
    await page
      .getByRole('dialog')
      .getByRole('link', { name: 'Banking', exact: true })
      .click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  }
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Banking')
  await expect(
    page.getByText('Your banking workspace starts here', { exact: true }),
  ).toBeVisible()
})

test('keyboard search focuses, filters, navigates and closes', async ({
  page,
}) => {
  await page.goto('/')
  await page.keyboard.press('Control+k')
  await expect(
    page.getByRole('textbox', { name: 'Search pages' }),
  ).toBeFocused()
  await page.getByRole('textbox').fill('recon')
  const link = page
    .getByRole('dialog')
    .getByRole('link', { name: /Reconciliation/ })
  await page.keyboard.press('Tab')
  await expect(link).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Reconciliation',
  )
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toBeFocused()
  await page.goBack()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Operations overview',
  )
})

test('deep links and unknown routes provide functional empty states', async ({
  page,
}) => {
  await page.route('**/reconciliation-api/incidents/detect', (route) =>
    route.fulfill({ json: { airflow: null } }),
  )
  for (const route of ['reconciliation']) {
    await page.goto('/' + route)
    await expect(
      page.getByText(
        'Airflow evidence is not configured. No reconciliation result is available.',
        { exact: true },
      ),
    ).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Refresh evidence' }),
    ).toBeEnabled()
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true)
  }
  await page.goto('/unknown')
  await page.getByRole('link', { name: /Back to overview/ }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Operations overview',
  )
})

test('reduced motion and guide work without changing system settings', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  expect(
    await page
      .locator('.workspace-body')
      .evaluate((element) => getComputedStyle(element).transitionDuration),
  ).toBe('0s')
  await page
    .getByRole('button', { name: 'About this workspace' })
    .first()
    .click()
  await expect(page.getByRole('dialog')).toContainText(
    'Banking connects to the configured API',
  )
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
})

test('skip link and a genuinely delayed page import remain accessible', async ({
  page,
}, testInfo) => {
  await page.route('**/src/pages/Banking.tsx*', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 600))
    await route.continue()
  })
  await page.goto('/')
  await page.keyboard.press('Tab')
  await expect(
    page.getByRole('link', { name: 'Skip to content' }),
  ).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
  if (testInfo.project.name === 'mobile') {
    await page.getByRole('button', { name: 'Open navigation' }).click()
    await page
      .getByRole('dialog')
      .getByRole('link', { name: 'Banking', exact: true })
      .click()
  } else {
    await page
      .getByRole('navigation', { name: 'Main navigation' })
      .getByRole('link', { name: 'Banking', exact: true })
      .click()
  }
  await expect(
    page.getByRole('status', { name: 'Loading workspace' }),
  ).toBeVisible()
  await expect(
    page.getByText('Your banking workspace starts here', { exact: true }),
  ).toBeVisible()
})

test('navigation controls stay reachable on a short laptop viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 650 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Collapse sidebar' }).click()
  await expect(
    page.getByRole('button', { name: 'Expand sidebar' }),
  ).toBeInViewport()
  await page.getByRole('button', { name: 'Expand sidebar' }).click()
  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('link', { name: 'Banking', exact: true })
    .click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Banking')
})
