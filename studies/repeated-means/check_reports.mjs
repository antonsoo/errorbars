// Inspect actual before/after CLI exports offline, including all downloaded observations.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';

const directory = resolve(process.argv[2]);
const output = resolve(process.argv[3]);
const expectedP = Number(process.argv[4]);
assert([0, 1].includes(expectedP));
await mkdir(output, { recursive: true });
const require = createRequire(new URL('../../web/package.json', import.meta.url));
const axe = await readFile(require.resolve('axe-core/axe.min.js'), 'utf8');
const results = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    for (const width of [375, 1280]) {
      const colorScheme = width === 375 ? 'light' : 'dark';
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme, offline: true });
      try {
        const page = await context.newPage();
        for (const scenario of ['constant', 'same_distribution', 'inspect']) {
          const errors = [], network = [];
          const onError = error => errors.push(error.message);
          const onRequest = request => { if (/^https?:/.test(request.url())) network.push(request.url()); };
          page.on('pageerror', onError);
          page.on('request', onRequest);
          await page.goto(pathToFileURL(join(directory, `${scenario}.html`)).href);
          await page.locator('#question-rows tr').first().waitFor();
          assert.equal(await page.locator('#question-rows tr').count(), 20);
          const waiting = page.waitForEvent('download');
          await page.getByRole('button', { name: 'Download evidence (JSON)', exact: true }).click();
          const downloaded = await waiting;
          const data = JSON.parse(await readFile(await downloaded.path(), 'utf8'));
          assert.equal(data.inference.p_value, expectedP);
          assert.equal(data.comparison.mean_diff === 0, expectedP === 1);
          assert.equal(data.questions.length, 20);
          assert(data.questions.every(q => (q.difference === 0) === (expectedP === 1)));
          if (scenario === 'inspect') {
            assert.equal(data.cohort.n_identity_matching, 20);
            assert(data.questions.every(q => q.observations_a.length === 1 && q.observations_b.length === 3));
            assert(data.questions.every(q => [...q.observations_a, ...q.observations_b].every(o => o.score === 0.1)));
          }
          let screenshot = null;
          if (engine === 'chromium' && scenario === 'inspect') {
            screenshot = `chromium-${width}.png`;
            await page.screenshot({ path: join(output, screenshot) });
          }
          await page.getByRole('button', { name: 'Inspect question q00', exact: true }).focus();
          await page.keyboard.press('Enter');
          assert(await page.locator('#inspector-heading').evaluate(el => el === document.activeElement));
          assert.match(await page.getByRole('region', { name: 'B observed generations' }).innerText(), /0\.1/);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          await page.evaluate(axe);
          const violations = await page.evaluate(async () => (await window.axe.run(document, {
            runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice'] },
          })).violations.map(v => v.id));
          assert.deepEqual(violations, []);
          assert.deepEqual(errors, []);
          assert.deepEqual(network, []);
          results.push({ engine, browserVersion: browser.version(), width, colorScheme, scenario,
            expectedP, offline: true, errors, network, accessibilityViolations: violations,
            htmlSha256: createHash('sha256').update(await readFile(join(directory, `${scenario}.html`))).digest('hex'),
            downloadedDifference: data.comparison.mean_diff, screenshot });
          page.off('pageerror', onError);
          page.off('request', onRequest);
        }
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}
await writeFile(join(output, 'browser.json'), JSON.stringify(results, null, 2) + '\n');
console.log(`${results.length} offline report/download workflows passed with selected p=${expectedP}.`);
