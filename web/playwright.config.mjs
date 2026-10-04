import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: true,
  workers: 2,
  timeout: 30_000,
  expect: { timeout: 5000 },
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:4197/errorbars/', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
  ],
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4197 --strictPort',
    wait: { stdout: /Local:/ },
    reuseExistingServer: false,
  },
});
