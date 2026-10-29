import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
process.env.PLAYWRIGHT_BROWSERS_PATH ??= resolve(
  import.meta.dirname,
  '.cache/ms-playwright',
)
export default defineConfig({
  outputDir: 'test-results/live',
  testDir: './e2e/live',
  testMatch: 'banking.live.ts',
  workers: 1,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:5174',
    viewport: { width: 1440, height: 1000 },
  },
})
