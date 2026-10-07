import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/reports',
  globalSetup: './tests/reports/setup.mjs',
  fullyParallel: true,
  workers: 2,
  timeout: 30_000,
  reporter: [['list']],
  use: { trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
  ],
});
