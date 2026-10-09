// Check replay.py's installed-package reports from disk with networking disabled.
// node examples/inspect-comparison/check-reports.mjs REPORT_DIRECTORY [SCREENSHOT_DIRECTORY]
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';

const directory = resolve(process.argv[2]);
const screenshots = resolve(process.argv[3] ?? directory);
await mkdir(screenshots, { recursive: true });
const results = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of [1440, 375]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, offline: true });
      const page = await context.newPage();
      const errors = [], requests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => {
        if (/^https?:/.test(request.url())) requests.push(request.url());
      });
      for (const [name, shared, matching, conflicting] of [
        ['solver-variant', 24, 24, 0],
        ['different-questions', 24, 0, 24],
        ['selected-epochs', 3, 3, 0],
      ]) {
        await page.goto(pathToFileURL(join(directory, `${name}.html`)).href);
        await page.locator('#question-rows tr').first().waitFor();
        assert.match(await page.locator('#identity-note').innerText(), new RegExp(`${matching} matching`));
        if (conflicting) {
          assert.match(await page.locator('#inference-description').innerText(), /conflicting question content/);
          await page.getByLabel('Show questions').selectOption('conflicting');
          assert.equal(await page.locator('#question-rows tr').count(), 24);
          if (engine === 'chromium') {
            await page.screenshot({ path: join(screenshots, `inspect-conflict-${width}.png`), fullPage: false });
          }
        }
        const qid = name === 'selected-epochs' ? 'q02' : 'q01';
        const inspect = page.getByRole('button', { name: `Inspect question ${qid}`, exact: true });
        await inspect.focus();
        await page.keyboard.press('Enter');
        assert.equal(await page.locator('#inspector-heading').evaluate(el => document.activeElement === el), true);
        assert.match(await page.locator('#inspector').innerText(), /Score: match/);
        assert.match(await page.locator('#inspector').innerText(), /record/);
        const waiting = page.waitForEvent('download');
        await page.getByRole('button', { name: 'Download evidence (JSON)', exact: true }).click();
        const exported = await waiting;
        const raw = await readFile(await exported.path(), 'utf8');
        const data = JSON.parse(raw);
        assert.equal(data.cohort.n_shared, shared);
        assert.equal(data.cohort.n_identity_matching, matching);
        assert.equal(data.cohort.n_identity_conflicting, conflicting);
        assert.equal(data.questions.filter(q => q.identity === 'conflicting').length, conflicting);
        assert.equal(data.comparison === null, conflicting > 0);
        if (name === 'selected-epochs') {
          assert.equal(data.comparison.n, 3);
          assert.equal(data.cohort.n_shared_observations_b, 6);
          assert.equal(data.questions.find(q => q.question_id === 'q02').observations_b.length, 2);
        }
        assert.ok(!raw.includes('What is ') && !raw.includes('/home/'));
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await writeFile(join(directory, `${engine}-${width}-${name}.json`), raw);
        results.push({ engine, width, name, shared, matching, conflicting });
      }
      assert.deepEqual(errors, []);
      assert.deepEqual(requests, []);
      await context.close();
    }
  } finally {
    await browser.close();
  }
}
await writeFile(join(directory, 'browser-results.json'), `${JSON.stringify(results, null, 2)}\n`);
console.log(`${results.length} offline browser workflows passed; exports agree with the recorded cohorts.`);
