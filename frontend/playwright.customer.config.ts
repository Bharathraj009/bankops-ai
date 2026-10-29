import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve(
  import.meta.dirname,
  '.cache/ms-playwright',
)
export default defineConfig({
  testDir: './e2e/live',
  testMatch: 'customer.live.ts',
  outputDir: 'test-results/customer-live',
  workers: 1,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:5184',
    viewport: { width: 1440, height: 1000 },
    trace: 'off',
    video: 'off',
  },
})
