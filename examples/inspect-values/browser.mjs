import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox, expect } from '../../web/node_modules/@playwright/test/index.mjs';
import AxeBuilder from '../../web/node_modules/@axe-core/playwright/dist/index.mjs';
const directory = resolve(process.argv[2]);
const output = resolve(process.argv[3]);
await mkdir(output, { recursive: true });
const results = [];
async function download(page, name) {
  const waiting = page.waitForEvent('download');
  await page.getByRole('button', { name, exact: true }).click();
  return await readFile(await (await waiting).path(), 'utf8');
}
// The summary CSV always quotes cells; parse the actual download independently.
function csv(text) {
  const rows = []; let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') { if (quoted && text[i + 1] === '"') { field += '"'; i++; } else quoted = !quoted; }
    else if (!quoted && char === ',') { row.push(field); field = ''; }
    else if (!quoted && char === '\r' && text[i + 1] === '\n') { row.push(field); rows.push(row); row = []; field = ''; i++; }
    else field += char;
  }
  assert.equal(quoted, false); assert.equal(field, ''); return rows;
}
for (const [engine, driver] of Object.entries({ chromium, firefox })) {
  const browser = await driver.launch();
  try {
    for (const width of [1440, 375]) {
      const context = await browser.newContext({ offline: true, viewport: { width, height: 1050 }, colorScheme: width === 1440 ? 'dark' : 'light' });
      const page = await context.newPage(); const errors = [], requests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
      await page.addInitScript(() => { window.csp = []; addEventListener('securitypolicyviolation', e => window.csp.push(e.violatedDirective)); });
      try {
        for (const key of ['correct', 'concise', 'words', 'conflict']) {
          const expected = JSON.parse(await readFile(join(directory, `${key}.json`)));
          const file = join(directory, `${key}.html`);
          await page.goto(pathToFileURL(file).href);
          await expect(page.locator('#question-rows tr')).toHaveCount(24);
          await expect(page.locator('#scoring-note')).toContainText('Selected values:');
          await expect(page.locator('#scoring-note')).toContainText(key === 'conflict' ? "'correct'" : `'${key}'`);
          if (key === 'conflict') {
            await expect(page.locator('#effect-value')).toHaveText('unavailable');
            await expect(page.locator('#scoring-note')).toContainText('24 conflicting');
          } else {
            await expect(page.locator('#scoring-note')).toContainText('24 matching');
            await expect(page.locator('#effect-value')).toHaveText(key === 'words' ? '+2.0000' : key === 'correct' ? '-0.3333' : '-0.6667');
          }
          const question = page.getByRole('button', { name: 'Inspect question q01', exact: true });
          await question.focus(); await page.keyboard.press('Enter');
          await expect(page.locator('#inspector-heading')).toBeFocused();
          await expect(page.getByRole('region', { name: 'A observed generations' })).toContainText(`Selected value: ${key === 'conflict' ? 'correct' : key}`);
          await expect(page.getByRole('region', { name: 'B observed generations' })).toContainText(`Selected value: ${key === 'conflict' ? 'concise' : key}`);
          if (key === 'correct') {
            assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations, []);
            if (!process.argv.includes('--no-screenshots')) {
              await page.screenshot({ path: join(output, `${engine}-${width}.png`), fullPage: true });
            }
          }
          await page.getByLabel('Search question or cluster').fill('q01');
          await expect(page.locator('#question-rows tr')).toHaveCount(1);
          assert.deepEqual(JSON.parse(await download(page, 'Download evidence (JSON)')), expected);
          const rows = csv(await download(page, 'Download shown questions (CSV)'));
          assert.equal(rows.length, 2);
          for (const [side, name] of [['a', key === 'conflict' ? 'correct' : key], ['b', key === 'conflict' ? 'concise' : key]]) {
            assert.deepEqual(JSON.parse(rows[1][rows[0].indexOf(`scorer_values_${side}`)]), [{ scorer: 'inspect:answer_dimensions', value: name }]);
          }
          await page.locator('#theme').click();
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
          assert.deepEqual(await page.evaluate(() => window.csp), []);
          const bytes = await readFile(file);
          results.push({ engine, browser: browser.version(), width, key, offline: true, downloads: 2,
            selectedValues: expected.score_values, effect: expected.cohort.mean_difference,
            html: { bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') },
            originalScoresAndSelectionRetained: true, filteredCsvRows: 1, pageErrors: [...errors], externalRequests: [...requests] });
        }
        assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
await writeFile(join(output, 'observations.json'), JSON.stringify({ workflows: results }, null, 2) + '\n');
console.log(`${results.length} offline workflows; ${results.length * 2} downloads verified`);
