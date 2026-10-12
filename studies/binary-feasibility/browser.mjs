// Run against a built site. Each page finishes loading before its local server
// is physically stopped; every edit and download then runs offline.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile, stat } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, extname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(resolve(here, '../../web/package.json'));
const { chromium, firefox } = require('playwright');
const { default: AxeBuilder } = require('@axe-core/playwright');
const [distArg, outputArg, expectation] = process.argv.slice(2);
assert(['before', 'after'].includes(expectation));
const dist = resolve(distArg), output = resolve(outputArg);
await mkdir(output, { recursive: true });
const records = [];
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
for (const [engine, launcher] of Object.entries({ chromium, firefox })) {
  const browser = await launcher.launch();
  for (const width of [1440, 375]) {
    const served = new Map();
    const server = createServer(async (req, res) => {
      try {
        const path = new URL(req.url, 'http://localhost').pathname;
        assert(path.startsWith('/errorbars/'));
        let file = resolve(dist, decodeURIComponent(path.slice('/errorbars/'.length)) || 'index.html');
        assert(file.startsWith(dist + '/'));
        if ((await stat(file)).isDirectory()) file = resolve(file, 'index.html');
        const bytes = await readFile(file);
        served.set(file.slice(dist.length + 1), { sha256: sha(bytes), bytes: bytes.length });
        res.writeHead(200, { 'Content-Type': mime[extname(file)] ?? 'application/octet-stream' });
        res.end(bytes);
      } catch { res.writeHead(404); res.end(); }
    });
    await new Promise(done => server.listen(0, '127.0.0.1', done));
    const origin = `http://127.0.0.1:${server.address().port}`;
    const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
    const page = await context.newPage();
    const errors = [], external = [], offlineRequests = [];
    let stopped = false;
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', req => {
      if (!/^https?:/.test(req.url())) return;
      if (new URL(req.url()).origin !== origin) external.push(req.url());
      if (stopped) offlineRequests.push(req.url());
    });
    await page.addInitScript(() => {
      window.cspViolations = [];
      document.addEventListener('securitypolicyviolation', e => window.cspViolations.push(e.violatedDirective));
    });
    await page.goto(origin + '/errorbars/');
    await page.locator('#result-n').filter({ hasText: '3,053' }).waitFor();
    await page.evaluate(() => document.fonts.ready);
    server.closeAllConnections();
    await new Promise(done => server.close(done));
    stopped = true;
    await context.setOffline(true);
    const states = [];
    for (const [name, mode, values, unavailable] of [
      ['impossible-pair', 'Questions needed', { baseline: '90', delta: '5', rho: '0.9' }, true],
      ['valid-budget', 'Gap my budget can detect', { baseline: '90', rho: '0.5', budget: '135' }, false],
      ['negative-minimum', 'Gap my budget can detect', { baseline: '20', rho: '-0.5', budget: '1000' }, false],
    ]) {
      await page.getByRole('radio', { name: mode, exact: true }).check();
      for (const [key, value] of Object.entries(values)) await page.locator(`#${key}`).fill(value);
      const disabled = await page.locator('#download-plan').isDisabled();
      assert.equal(disabled, expectation === 'after' && unavailable);
      const state = { name, disabled, resultVisible: await page.locator('#plan-output').isVisible(),
        error: await page.locator('#input-error').innerText(),
        warnings: await page.locator('#plan-warnings').innerText(),
        table: await page.locator('#budget-rows').innerText() };
      if (!disabled) {
        const pending = page.waitForEvent('download');
        await page.locator('#download-plan').click();
        const download = await pending;
        const bytes = await readFile(await download.path());
        state.plan = JSON.parse(bytes.toString());
        state.download = `${engine}-${width}-${name}.json`;
        await writeFile(resolve(output, state.download), bytes);
        state.downloadSha256 = sha(bytes);
        if (expectation === 'after') {
          assert.equal(state.plan.schemaVersion, 2);
          if (name === 'valid-budget') assert.equal(state.plan.sensitivity.minimumDetectableEffect, null);
          if (name === 'negative-minimum') assert.equal(state.plan.result.correlationLimited, true);
        }
        assert(!/NaN|Infinity/.test(await page.locator('#chart svg').innerHTML()));
      }
      state.overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      assert.equal(state.overflow, false);
      const audit = await new AxeBuilder({ page }).analyze();
      state.accessibilityViolations = audit.violations;
      assert.equal(audit.violations.length, 0);
      if ((width === 1440 && name === 'impossible-pair') || (width === 375 && name === 'negative-minimum')) {
        state.screenshot = `${engine}-${width}-${name}.png`;
        await page.screenshot({ path: resolve(output, state.screenshot), fullPage: true });
      }
      states.push(state);
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert.deepEqual(offlineRequests, []);
    const cspViolations = await page.evaluate(() => window.cspViolations);
    assert.deepEqual(cspViolations, []);
    records.push({ engine, version: browser.version(), width, states, errors, external, offlineRequests,
      cspViolations, physicallyStoppedServer: true, served: Object.fromEntries(served) });
    await context.close();
  }
  await browser.close();
}
await writeFile(resolve(output, 'browser.json'), JSON.stringify({ expectation, records }, null, 2) + '\n');
console.log(`Verified ${records.length} offline browser/viewport workflows (${expectation}).`);
