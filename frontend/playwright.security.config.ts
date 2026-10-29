import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve(
  import.meta.dirname,
  '.cache/ms-playwright',
)
export default defineConfig({
  testDir: './e2e/live',
  testMatch: ['customer.live.ts', 'security.live.ts'],
  outputDir: 'test-results/security-live',
  workers: 1,
  retries: 0,
  timeout: 60000,
  use: {
    baseURL: 'http://127.0.0.1:5196',
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
})
