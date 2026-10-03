import { defineConfig } from '@playwright/test'

// Deterministic, fully local: a stateless feed-api stub plus two `next start`
// instances built once. Never reuses a server it did not start.
export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.e2e\.ts$/,
  snapshotDir: './e2e/__baseline__',
  snapshotPathTemplate: '{snapshotDir}/{arg}{ext}',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:3100', browserName: 'chromium' },
  webServer: [
    {
      command: 'node e2e/stub/feed-api-stub.mjs',
      url: 'http://127.0.0.1:4010/health',
      reuseExistingServer: false,
    },
    {
      command: 'node e2e/stub/launch-apps.mjs',
      url: 'http://127.0.0.1:3100',
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
})
