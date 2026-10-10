// Inspect installed-package reports offline, including the exported evidence.
// node examples/inspect-scoring/check-reports.mjs REPORT_DIRECTORY [SCREENSHOT_DIRECTORY]
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
      for (const name of ['anywhere', 'includes', 'exact-repeat', 'improved-exact']) {
        const conflict = ['anywhere', 'includes'].includes(name);
        await page.goto(pathToFileURL(join(directory, `${name}.html`)).href);
        await page.locator('#question-rows tr').first().waitFor();
        assert.match(await page.locator('#identity-note').innerText(), /24 matching/);
        assert.match(await page.locator('#scoring-note').innerText(),
          conflict ? /24 conflicting/ : /24 matching/);
        if (conflict) {
          assert.equal(await page.locator('#effect-value').innerText(), 'unavailable');
          assert.match(await page.locator('#inference-description').innerText(), /conflicting scoring rules/);
          await page.getByLabel('Show questions').selectOption('conflicting');
          assert.equal(await page.locator('#question-rows tr').count(), 24);
          if (engine === 'chromium' && name === 'anywhere') {
            await page.screenshot({ path: join(screenshots, `scoring-conflict-${width}.png`) });
          }
        }
        const opener = page.getByRole('button', { name: 'Inspect question q01', exact: true });
        await opener.focus();
        await page.keyboard.press('Enter');
        assert.equal(await page.locator('#inspector-heading').evaluate(el => document.activeElement === el), true);
        assert.match(await page.locator('#inspector').innerText(), /Question identity: matching/);
        assert.match(await page.locator('#inspector').innerText(), /Scorer: inspect:match/);
        const a = page.getByRole('region', { name: 'A observed generations' });
        await a.getByText('Scorer configuration fingerprint', { exact: true }).click();
        assert.match(await a.innerText(), /inspect-params-v1:/);
        if (conflict) {
          assert.match(await page.locator('#inspector').innerText(), /Conflicting scoring rules/);
          assert.doesNotMatch(await page.locator('#inspector').innerText(), /Conflicting question content/);
        }
        const waiting = page.waitForEvent('download');
        await page.getByRole('button', { name: 'Download evidence (JSON)', exact: true }).click();
        const downloaded = await waiting;
        const raw = await readFile(await downloaded.path(), 'utf8');
        const data = JSON.parse(raw);
        assert.equal(data.comparison === null, conflict);
        assert.equal(data.cohort.n_scoring_conflicting, conflict ? 24 : 0);
        assert.equal(data.cohort.n_identity_matching, 24);
        assert.equal(data.questions.length, 24);
        assert.equal(data.questions.filter(q => q.scoring === 'conflicting').length, conflict ? 24 : 0);
        assert.ok(data.questions.every(q => q.observations_a[0].scorer_config.startsWith('inspect-params-v1:')));
        const q = data.questions.find(q => q.question_id === 'q01');
        assert.equal(q.observations_a[0].score, 0);
        assert.equal(q.observations_b[0].score, name === 'exact-repeat' ? 0 : 1);
        if (!conflict) assert.equal(data.inference.p_value, name === 'exact-repeat' ? 1 : 0.0078125);
        assert.ok(!raw.includes('What is ') && !raw.includes('The answer is ') && !raw.includes('/home/'));
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await writeFile(join(directory, `${engine}-${width}-${name}.json`), raw);
        results.push({ engine, width, name, questions: 24, inferenceAvailable: !conflict,
          scorerConflicts: conflict ? 24 : 0, networkRequests: requests.length, pageErrors: errors.length });
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
console.log(`${results.length} offline workflows passed; downloaded scoring evidence matches retained logs.`);
