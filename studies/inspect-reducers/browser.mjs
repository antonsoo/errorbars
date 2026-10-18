// Open actual installed CLI reports offline, inspect source scores and save downloads.
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const [artifactsArg, outputArg, phase = 'after'] = process.argv.slice(2);
assert(artifactsArg && outputArg && ['before', 'after'].includes(phase),
  'Use browser.mjs ARTIFACTS OUTPUT [before|after]');
const artifacts = resolve(artifactsArg), output = resolve(outputArg);
await mkdir(output, { recursive: true });
const cases = phase === 'before' ? ['max'] : ['max', 'pass_at_2', 'mean', 'max-roundtrip', 'named-max-correct'];
const records = [], files = {};
for (const name of cases) {
  const bytes = await readFile(join(artifacts, `${name}.html`));
  files[name] = { bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
}
for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch({ headless: true });
  for (const width of [1440, 375]) {
    for (const report of cases) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, acceptDownloads: true,
        colorScheme: name === 'firefox' ? 'dark' : 'light' });
      await context.setOffline(true);
      const page = await context.newPage();
      const errors = [], requests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
      await page.goto(pathToFileURL(join(artifacts, `${report}.html`)).href);
      await page.locator('#question-rows tr').first().waitFor();
      const data = JSON.parse(await page.locator('#report-data').textContent());
      const mean = phase === 'before' || report === 'mean';
      const pass = report === 'pass_at_2';
      assert.equal(data.questions.length, 24);
      assert.equal(data.comparison.mean_a, mean ? 1 / 3 : pass ? 2 / 3 : 1);
      assert.equal(data.comparison.mean_b, .75);
      assert.equal(data.inference.test, mean || pass ? 'paired_t' : 'mcnemar_exact');
      if (!mean && !pass) assert.equal(data.inference.p_value, .03125);
      assert.equal(data.cohort.n_observations_a, mean ? 72 : 24);
      if (!mean) {
        const reducer = pass ? 'pass_at_2' : 'max';
        assert(data.score_values.every(row => row.scorer.includes(`epoch reducer=${reducer}; epochs=3`)));
        assert(data.questions.every(q => q.observations_a.length === 1 && q.observations_b.length === 1));
        if (report.includes('named')) assert(data.score_values.every(row => row.scorer_value === 'correct'));
        if (!report.endsWith('roundtrip')) assert(data.questions.every(q =>
          [...q.observations_a, ...q.observations_b].every(obs => obs.metric.includes('reductions[0].samples'))));
      }
      const inference = await page.locator('#inference-description').textContent();
      if (report === 'max') await page.screenshot({ path: join(output, `${name}-${width}-summary.png`), fullPage: true });
      await page.getByLabel('Search question or cluster').fill('q00');
      assert.equal(await page.locator('#question-rows tr').count(), 1);
      const button = page.getByRole('button', { name: 'Inspect question q00', exact: true });
      await button.focus(); await page.keyboard.press('Enter');
      await page.locator('#inspector-heading').waitFor();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      if (phase === 'after' && report === 'max') {
        assert((await page.locator('#inspector').textContent()).includes('reductions[0].samples'));
      }
      if (report === 'max' || (phase === 'after' && report === 'pass_at_2' && width === 1440)
        || (phase === 'after' && report === 'mean' && width === 375)) {
        await page.locator('#inspector').screenshot({ path: join(output, `${name}-${width}-${report}-inspector.png`) });
      }
      await page.getByRole('button', { name: 'Back to question', exact: true }).click();
      const downloads = [];
      for (const [label, suffix] of [['Download evidence (JSON)', 'json'], ['Download shown questions (CSV)', 'csv']]) {
        const pending = page.waitForEvent('download');
        await page.getByRole('button', { name: label, exact: true }).click();
        const path = join(output, `${name}-${width}-${report}.${suffix}`);
        await (await pending).saveAs(path);
        const bytes = await readFile(path);
        if (suffix === 'json') assert.deepEqual(JSON.parse(bytes.toString('utf8')), data);
        else {
          assert.equal(bytes.toString('utf8').trim().split('\r\n').length, 2);
          assert(bytes.includes(Buffer.from('"q00"')));
          if (!mean) assert(bytes.includes(Buffer.from(`epoch reducer=${pass ? 'pass_at_2' : 'max'}`)));
        }
        downloads.push({ file: path.split('/').at(-1), bytes: bytes.length,
          sha256: createHash('sha256').update(bytes).digest('hex') });
      }
      assert.equal(await page.locator('#inference-description').textContent(), inference);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      records.push({ browser: name, version: browser.version(), width, report, phase,
        offline_before_load: true, questions: 24, observations_per_run: mean ? 72 : 24,
        means: [data.comparison.mean_a, data.comparison.mean_b],
        test: data.inference.test, p: data.inference.p_value,
        keyboard_inspected: 'q00', inference_unchanged_after_filter: true,
        downloads, horizontal_overflow: false, errors, network_requests: requests });
      await context.close();
    }
  }
  await browser.close();
}
await writeFile(join(output, 'browser.json'), JSON.stringify({ phase, files, workflows: records }, null, 2) + '\n');
console.log(JSON.stringify({ workflows: records.length, downloads_checked: records.length * 2 }));
