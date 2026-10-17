// Inspect production bytes with cached browsers; no source modules or network services.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, join, extname, sep } from 'node:path';
import { chromium, firefox } from '../../web/node_modules/@playwright/test/index.mjs';

const [distArg, phase, outArg] = process.argv.slice(2);
assert(distArg && ['before', 'after'].includes(phase) && outArg, 'usage: browser.mjs DIST before|after OUT');
const dist = resolve(distArg), out = resolve(outArg), served = new Map();
const partial = '20260901_mini-v2.4.2_gemini-3-5-flash';
const peer = '20251205_sonar-foundation-agent_claude-opus-4-5';
const native = JSON.parse(await readFile(new URL('native/partial-details.json', import.meta.url), 'utf8'));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };
await mkdir(out, { recursive: true });
const server = createServer(async (req, res) => {
  try {
    const relative = decodeURIComponent(new URL(req.url, 'http://localhost').pathname).replace(/^\/errorbars\//, '');
    const path = resolve(dist, relative);
    assert(path.startsWith(dist + sep));
    const bytes = await readFile(path);
    served.set(relative, { path: relative, bytes: bytes.length, sha256: sha(bytes) });
    res.writeHead(200, { 'Content-Type': mime[extname(path)] ?? 'application/octet-stream' }); res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}/errorbars/swe-bench.html`;
const results = [];
try {
  for (const [name, engine] of [['chromium', chromium], ['firefox', firefox]]) {
    const browser = await engine.launch();
    try {
      for (const width of [375, 1440]) {
        const context = await browser.newContext({ viewport: { width, height: 1050 } });
        try {
          const page = await context.newPage(), errors = [], external = [], offlineRequests = [];
          let offline = false;
          page.on('pageerror', error => errors.push(error.message));
          page.on('request', request => {
            if (!/^https?:/.test(request.url())) return;
            if (new URL(request.url()).origin !== new URL(base).origin) external.push(request.url());
            if (offline) offlineRequests.push(request.url());
          });
          await page.goto(`${base}?a=${partial}&b=${peer}`);
          await page.locator('#verdict').waitFor();
          await page.evaluate(async () => {
            await document.fonts.ready;
            await Promise.all([...document.images].map(async image => { image.loading = 'eager'; await image.decode(); }));
          });
          const options = await page.locator('#pick-a option').evaluateAll(nodes => nodes.map(n => n.value));
          const record = { browser: name, width, phase, submissionCount: await page.locator('#submission-count').textContent(),
            partialSelectable: options.includes(partial), selectedA: await page.locator('#pick-a').inputValue(),
            selectedB: await page.locator('#pick-b').inputValue(), verdict: await page.locator('#verdict').textContent(),
            detail: await page.locator('#verdict-detail').textContent(), table: await page.locator('#result-table').textContent() };
          if (phase === 'before') {
            assert(record.partialSelectable && record.selectedA === partial);
            assert.equal(record.submissionCount, '173');
            assert.match(record.table, /71\.8% \(359 of 500\)/);
            assert.equal(record.verdict, 'Different on tasks like these.');
            const cells = await page.locator('#task-grid .cell').evaluateAll(nodes => nodes.map(n => ({ id: n.title.split(':')[0], kind: n.className })));
            const unreported = cells.filter(c => !Object.hasOwn(native, c.id));
            assert.equal(unreported.length, 59);
            assert(unreported.every(c => c.kind === 'cell cell-b' || c.kind === 'cell cell-none'));
            record.unreportedTasksShownAsFailures = unreported.length;
            record.unreportedTasksShownAsPeerOnlySuccesses = unreported.filter(c => c.kind === 'cell cell-b').length;
          } else {
            assert(!record.partialSelectable && record.selectedA !== partial && record.selectedB === peer);
            assert.equal(record.submissionCount, '172');
            assert.match(await page.locator('.abstract').textContent(), /441-task report is excluded/);
            await page.locator('#pick-a').selectOption('20260217_mini-v2.0.0_claude-4-5-opus-high');
            await page.locator('#pick-b').selectOption('20260217_mini-v2.0.0_gpt-5-2-high');
            assert.equal(await page.locator('#verdict').textContent(), 'Different on tasks like these.');
            assert.match(await page.locator('#result-table').textContent(), /\+4\.0 points/);
          }
          record.horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
          assert(!record.horizontalOverflow);
          if (phase === 'after' || (name === 'chromium' && width === 1440) || (name === 'firefox' && width === 375)) {
            await page.screenshot({ path: join(out, `${phase}-${name}-${width}.png`) });
          }
          await context.setOffline(true); offline = true;
          await page.locator('#swap').click();
          assert.equal(await page.locator('#task-grid .cell').count(), 500);
          await page.getByText('Use a run of my own as A').click();
          await page.locator('#own-ids').fill(JSON.stringify({ resolved_ids: Object.keys(native).slice(0, 2) }));
          await page.locator('#own-apply').click();
          assert.match(await page.locator('#own-status').textContent(), /2 of 500 tasks resolved/);
          assert.equal(await page.locator('#task-grid .cell').count(), 500);
          record.resolvedOnlyOwnRunKeepsFullBenchmarkConvention = true;
          record.errors = errors; record.externalRequests = external; record.offlineRequests = offlineRequests;
          assert.deepEqual(errors, []); assert.deepEqual(external, []); assert.deepEqual(offlineRequests, []);
          results.push(record);
        } finally { await context.close(); }
      }
    } finally { await browser.close(); }
  }
} finally { await new Promise(resolve => server.close(resolve)); }
await writeFile(join(out, `${phase}-browser.json`), JSON.stringify({ phase, scenarios: results, served: [...served.values()] }, null, 2) + '\n');
console.log(JSON.stringify({ phase, scenarios: results.length, servedFiles: served.size }));
