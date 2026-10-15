// Open actual installed-wheel reports offline before the first load.
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
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
const hashes = {};
for (const file of ['folded-native.html', 'improved-strict-native.html']) {
  const bytes = await readFile(join(artifacts, file));
  hashes[file] = { sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length };
}
const records = [];
for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch({ headless: true });
  for (const width of [1440, 375]) {
    for (const label of ['folded', 'improved-strict']) {
      const conflict = label === 'folded';
      const context = await browser.newContext({ viewport: { width, height: 1000 },
        colorScheme: name === 'firefox' ? 'dark' : 'light', acceptDownloads: true });
      await context.setOffline(true);
      const page = await context.newPage();
      const errors = [], requests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
      await page.goto(pathToFileURL(join(artifacts, `${label}-native.html`)).href);
      await page.locator('#question-rows tr').first().waitFor();
      assert.equal(await page.locator('#effect-value').textContent(), conflict ? 'unavailable' : '-0.3333');
      const expected = JSON.parse(await page.locator('#report-data').textContent());
      assert.equal(expected.questions.length, 24);
      assert.equal(expected.cohort.n_identity_matching, 24);
      assert.equal(expected.cohort[conflict ? 'n_scoring_conflicting' : 'n_scoring_matching'], 24);
      if (conflict) assert.equal(expected.comparison, null);
      else assert.equal(expected.inference.p_value, 0.0078125);
      const question = 'grading_contract-0';
      await page.getByLabel('Search question or cluster').fill(question);
      assert.equal(await page.locator('#question-rows tr').count(), 1);
      await page.getByRole('button', { name: `Inspect question ${question}`, exact: true }).click();
      await page.locator('#inspector-heading').waitFor();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const prefix = `${name}-${width}-${label}`;
      await page.screenshot({ path: join(output, `${prefix}.png`) });
      await page.getByRole('button', { name: 'Back to question', exact: true }).click();
      for (const [button, suffix] of [['Download evidence (JSON)', 'json'], ['Download shown questions (CSV)', 'csv']]) {
        const waiting = page.waitForEvent('download');
        await page.getByRole('button', { name: button, exact: true }).click();
        const download = await waiting;
        await download.saveAs(join(output, `${prefix}.${suffix}`));
        const text = await readFile(join(output, `${prefix}.${suffix}`), 'utf8');
        if (suffix === 'json') assert.deepEqual(JSON.parse(text), expected);
        else {
          assert.equal(text.trim().split('\r\n').length, 2);
          assert(text.includes('"scoring"'));
          assert(text.includes(`"${question}","","${conflict ? 'conflicting' : 'both'}","matching","${conflict ? 'conflicting' : 'matching'}"`));
        }
      }
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      records.push({ browser: name, version: browser.version(), width, case: label,
        offline_before_load: true, json_matches_complete_evidence: true, json_questions: 24,
        csv_filtered_questions: 1, csv_scoring_state_preserved: true, horizontal_overflow: false,
        inference: conflict ? 'withheld' : expected.inference.p_value, errors, network_requests: requests });
      await context.close();
    }
  }
  await browser.close();
}
await writeFile(join(output, 'browser.json'), JSON.stringify({ artifacts: hashes, workflows: records }, null, 2) + '\n');
console.log(JSON.stringify({ workflows: records.length, offline: true, downloads_checked: records.length * 2 }));
