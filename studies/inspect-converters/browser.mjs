// Exercise actual installed-wheel report files, disconnected before their first load.
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const [artifactsArg, outputArg] = process.argv.slice(2);
assert(artifactsArg && outputArg, 'Use browser.mjs ARTIFACTS OUTPUT');
const artifacts = resolve(artifactsArg), output = resolve(outputArg);
await mkdir(output, { recursive: true });
const records = [], hashes = {};
for (const file of ['default-native.html', 'plain-native.html', 'plain-roundtrip.html']) {
  const bytes = await readFile(join(artifacts, file));
  hashes[file] = { bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
}
for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch({ headless: true });
  for (const width of [1440, 375]) {
    for (const file of Object.keys(hashes)) {
      const context = await browser.newContext({ viewport: { width, height: 960 }, acceptDownloads: true,
        colorScheme: name === 'firefox' ? 'dark' : 'light' });
      await context.setOffline(true);
      const page = await context.newPage();
      const errors = [], requests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
      await page.goto(pathToFileURL(join(artifacts, file)).href);
      await page.locator('#question-rows tr').first().waitFor();
      const expected = JSON.parse(await page.locator('#report-data').textContent());
      assert.equal(expected.questions.length, 8);
      assert.equal(expected.comparison.mean_diff, 1);
      assert.equal(expected.inference.test, 'mcnemar_exact');
      assert.equal(expected.inference.p_value, 2 / 2 ** 8);
      if (file.startsWith('plain-')) assert(expected.score_values.every(row => row.scorer_value === 'plain'));
      await page.getByLabel('Search question or cluster').fill('q0');
      assert.equal(await page.locator('#question-rows tr').count(), 1);
      await page.getByRole('button', { name: 'Inspect question q0', exact: true }).click();
      await page.locator('#inspector-heading').waitFor();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      if (file === 'plain-native.html') await page.screenshot({ path: join(output, `${name}-${width}.png`) });
      await page.getByRole('button', { name: 'Back to question', exact: true }).click();
      for (const [button, suffix] of [['Download evidence (JSON)', 'json'], ['Download shown questions (CSV)', 'csv']]) {
        const pending = page.waitForEvent('download');
        await page.getByRole('button', { name: button, exact: true }).click();
        const path = join(output, `${name}-${width}-${file}.${suffix}`);
        await (await pending).saveAs(path);
        const text = await readFile(path, 'utf8');
        if (suffix === 'json') assert.deepEqual(JSON.parse(text), expected);
        else {
          assert.equal(text.trim().split('\r\n').length, 2);
          assert(text.includes('"q0"'));
        }
      }
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      records.push({ browser: name, version: browser.version(), width, file,
        offline_before_load: true, questions: 8, filtered_csv_questions: 1,
        downloaded_json_matches_report: true, selected_value_retained: file.startsWith('plain-') ? 'plain' : null,
        mean_difference: 1, exact_p: expected.inference.p_value,
        horizontal_overflow: false, errors, network_requests: requests });
      await context.close();
    }
  }
  await browser.close();
}
await writeFile(join(output, 'browser.json'), JSON.stringify({ artifacts: hashes, workflows: records }, null, 2) + '\n');
console.log(JSON.stringify({ workflows: records.length, downloads_checked: records.length * 2 }));
