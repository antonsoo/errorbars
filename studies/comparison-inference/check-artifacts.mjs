// Verify and capture installed HTML plus the production browser's real threshold case.
// node studies/comparison-inference/check-artifacts.mjs REPORT_DIRECTORY SITE_BASE_URL
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';

const directory = resolve(process.argv[2]);
const base = process.argv[3];
const results = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of [1440, 375]) {
      const context = await browser.newContext({ viewport: { width, height: 1100 }, colorScheme: 'light' });
      const page = await context.newPage();
      await context.setOffline(true);
      await page.goto(pathToFileURL(join(directory, 'two-wins.html')).href);
      assert.match(await page.locator('#inference-description').innerText(), /Exact McNemar p = 0.5000/);
      assert.match(await page.locator('#interval-chart').innerText(), /t approx\./);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.locator('.estimate').screenshot({ path: join(directory, `two-wins-${engine}-${width}.png`) });
      const report = await page.locator('#inference-description').innerText();
      await context.setOffline(false);
      await page.goto(`${base}swe-bench.html?a=20250928_trae_doubao_seed_code&b=20250901_warp`);
      await page.locator('#verdict').waitFor();
      assert.equal(await page.locator('#verdict').innerText(), 'No significant difference detected.');
      assert.match(await page.locator('#result-table').innerText(), /0\.060/);
      assert.match(await page.locator('#result-table').innerText(), /0\.045/);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.locator('#compare').screenshot({ path: join(directory, `swe-threshold-${engine}-${width}.png`) });
      results.push({ engine, width, report, site: await page.locator('#verdict-detail').innerText() });
      await context.close();
    }
  } finally {
    await browser.close();
  }
}
await writeFile(join(directory, 'browsers.json'), `${JSON.stringify(results, null, 2)}\n`);
console.log(`Verified ${results.length} offline-report / production-page scenarios`);
