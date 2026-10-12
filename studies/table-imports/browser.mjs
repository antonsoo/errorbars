// Open the actual CLI-generated report offline and inspect/download its evidence.
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox } from '../../web/node_modules/@playwright/test/index.mjs';

const [reportArg, outArg] = process.argv.slice(2);
assert(reportArg && outArg, 'usage: node browser.mjs REPORT.html OUTPUT_DIRECTORY');
const report = resolve(reportArg), out = resolve(outArg);
await mkdir(out, { recursive: true });
const results = [];
for (const [name, engine] of [['chromium', chromium], ['firefox', firefox]]) {
  const browser = await engine.launch({ headless: true });
  try {
    for (const width of [375, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 960 }, offline: true });
      try {
        const page = await context.newPage(), errors = [], requests = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
        await page.goto(pathToFileURL(report).href);
        await page.locator('#question-rows tr').first().waitFor();
        assert.equal(await page.locator('#effect-value').textContent(), '+0.2000');
        assert.equal(await page.locator('#question-rows tr').count(), 40);
        await page.getByRole('button', { name: /^Inspect question q00/ }).click();
        assert.match(await page.locator('#inspector').textContent(), /record 1 \/ lines 2-3/);
        assert.match(await page.locator('#inspector').textContent(), /record 2 \/ lines 4-5/);
        await page.getByRole('button', { name: 'Back to question', exact: true }).click();
        await page.getByLabel('Show questions').selectOption('a_higher');
        assert.equal(await page.locator('#question-rows tr').count(), 8);
        const downloads = {};
        for (const label of ['Download evidence (JSON)', 'Download shown questions (CSV)']) {
          const pending = page.waitForEvent('download');
          await page.getByRole('button', { name: label, exact: true }).click();
          const download = await pending;
          const bytes = await readFile(await download.path());
          await writeFile(join(out, `${name}-${width}-${download.suggestedFilename()}`), bytes);
          downloads[label] = bytes.length;
          if (label.endsWith('(JSON)')) {
            const data = JSON.parse(bytes);
            assert.equal(data.questions.length, 40);
            assert.equal(data.comparison.mean_diff, 0.2);
          }
        }
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        assert.deepEqual(errors, []); assert.deepEqual(requests, []);
        await page.screenshot({ path: join(out, `${name}-${width}.png`), fullPage: true });
        results.push({ browser: name, width, questions: 40, filtered: 8, downloads, errors, requests });
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
await writeFile(join(out, 'results.json'), JSON.stringify(results, null, 2) + '\n');
console.log(JSON.stringify({ offlineReports: results.length, downloads: results.length * 2 }));
