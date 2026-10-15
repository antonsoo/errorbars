// Inspect the installed package's actual SVG and standalone report, offline before first load.
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const options = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, args) => {
  if (index % 2 === 0) pairs.push([value.slice(2), args[index + 1]]);
  return pairs;
}, []));
assert(options.artifacts && options.out, 'Use --artifacts DIRECTORY --out DIRECTORY');
const artifacts = resolve(options.artifacts), output = resolve(options.out);
await mkdir(output, { recursive: true });
const records = [];
const hashes = {};
for (const file of ['loss.html', 'loss.svg', 'loss.json', 'loss.csv']) {
  const bytes = await readFile(join(artifacts, file));
  hashes[file] = { sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length };
}
for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch({ headless: true });
  for (const width of [1440, 375]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 },
      colorScheme: name === 'firefox' ? 'dark' : 'light', acceptDownloads: true });
    await context.setOffline(true);
    const page = await context.newPage();
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
    await page.goto(pathToFileURL(join(artifacts, 'loss.html')).href);
    await page.locator('#question-rows tr').first().waitFor();
    assert.equal(await page.locator('#effect-value').textContent(), '-0.5406');
    const expected = JSON.parse(await page.locator('#report-data').textContent());
    assert(expected.questions.every(q => [...q.observations_a, ...q.observations_b]
      .every(obs => obs.higher_is_better === false)));
    await page.getByLabel('Search question or cluster').fill('metric_contract-0');
    assert.equal(await page.locator('#question-rows tr').count(), 1);
    await page.getByRole('button', { name: 'Inspect question metric_contract-0', exact: true }).click();
    await page.locator('#inspector-heading').waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const prefix = `${name}-${width}`;
    await page.screenshot({ path: join(output, `${prefix}-report.png`) });
    await page.getByRole('button', { name: 'Back to question', exact: true }).click();
    for (const [label, file] of [['Download evidence (JSON)', `${prefix}.json`],
      ['Download shown questions (CSV)', `${prefix}.csv`]]) {
      const waiting = page.waitForEvent('download');
      await page.getByRole('button', { name: label, exact: true }).click();
      const download = await waiting;
      await download.saveAs(join(output, file));
      const text = await readFile(join(output, file), 'utf8');
      if (file.endsWith('.json')) assert.deepEqual(JSON.parse(text), expected);
      else {
        assert(text.includes('"higher_is_better_a","higher_is_better_b"'));
        assert(text.includes('"[false]","[false]"'));
        assert.equal(text.trim().split('\r\n').length, 2);
      }
    }
    await page.goto(pathToFileURL(join(artifacts, 'loss.svg')).href);
    assert((await page.locator('svg').textContent()).includes('lower scores first (recorded)'));
    assert.deepEqual(await page.locator('svg .model-row > title').allTextContents(), ['precise', 'noisy']);
    if (width === 1440) await page.locator('svg').screenshot({ path: join(output, `${name}-forest.png`) });
    assert.deepEqual(errors, []); assert.deepEqual(requests, []);
    records.push({ browser: name, version: browser.version(), width, offline_before_load: true,
      json_matches_complete_evidence: true, csv_filtered_questions: 1, csv_direction_preserved: true,
      report_horizontal_overflow: false, original_unit_difference: expected.comparison.mean_diff,
      svg_models_in_order: ['precise', 'noisy'], errors, network_requests: requests });
    await context.close();
  }
  await browser.close();
}
await writeFile(join(output, 'browser.json'), JSON.stringify({ artifacts: hashes, workflows: records }, null, 2) + '\n');
console.log(JSON.stringify({ workflows: records.length, offline: true, downloads_checked: records.length * 2 }));
