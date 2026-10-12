// Replay the CLI's exact report inputs through the built app, offline after loading.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, join, extname, sep } from 'node:path';
import { chromium, firefox } from '../../web/node_modules/@playwright/test/index.mjs';
const [distArg, casesArg, outArg, mode] = process.argv.slice(2);
assert(distArg && casesArg && outArg, 'usage: browser.mjs DIST CASES.json OUTPUT [--observe-only]');
const dist = resolve(distArg), out = resolve(outArg), observe = mode === '--observe-only';
const cases = JSON.parse(await readFile(casesArg, 'utf8')), served = new Map();
await mkdir(out, { recursive: true });
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };
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
const url = `http://127.0.0.1:${server.address().port}/errorbars/swe-bench.html`;
const results = [];
try {
  for (const [name, engine] of [['chromium', chromium], ['firefox', firefox]]) {
    const browser = await engine.launch();
    try {
      for (const width of [375, 1440]) {
        const context = await browser.newContext({ viewport: { width, height: 960 } });
        try {
          const page = await context.newPage(), errors = [], offlineRequests = [];
          let offline = false;
          page.on('pageerror', error => errors.push(error.message));
          page.on('request', request => { if (offline && /^https?:/.test(request.url())) offlineRequests.push(request.url()); });
          await page.goto(url);
          await page.locator('#verdict').waitFor();
          await page.evaluate(async () => { await Promise.all([...document.fonts].map(font => font.load())); });
          await page.evaluate(async () => {
            await Promise.all([...document.images].map(async image => { image.loading = 'eager'; await image.decode(); }));
          });
          await context.setOffline(true); offline = true;
          await page.getByText('Use a run of my own as A').click();
          const box = page.locator('#own-ids'), apply = page.locator('#own-apply');
          const rows = [];
          for (const [id, report, valid] of cases) {
            await box.fill(JSON.stringify({ resolved_ids: ['astropy__astropy-12907', 'django__django-11099'] }));
            await apply.click();
            const previous = await page.locator('#result-table').textContent();
            await box.fill(JSON.stringify(report)); await apply.click();
            const rejected = await page.locator('#own-status').evaluate(el => el.classList.contains('own-status-error'));
            const state = await page.locator('#result-table').textContent();
            const row = { id, valid, rejected, previousPreserved: state === previous,
              status: await page.locator('#own-status').textContent(), tableSha256: sha(state) };
            rows.push(row);
            if (!observe) {
              assert.equal(rejected, !valid, id);
              if (!valid) assert(row.previousPreserved, id);
            }
            if (!observe && id === 'null-primary') {
              await page.locator('#compare').screenshot({ path: join(out, `${name}-${width}.png`) });
            }
          }
          assert.deepEqual(errors, []); assert.deepEqual(offlineRequests, []);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          results.push({ browser: name, width, rows, errors, offlineRequests });
        } finally { await context.close(); }
      }
    } finally { await browser.close(); }
  }
} finally { await new Promise(resolve => server.close(resolve)); }
const summary = {
  malformedRejectedAndPreserved: results.flatMap(r => r.rows).filter(r => !r.valid && r.rejected && r.previousPreserved).length,
  validAccepted: results.flatMap(r => r.rows).filter(r => r.valid && !r.rejected).length,
  totalImports: results.flatMap(r => r.rows).length,
};
await writeFile(join(out, 'results.json'), JSON.stringify({ summary, results, served: [...served.values()].sort((a,b) => a.path.localeCompare(b.path)) }, null, 2) + '\n');
console.log(JSON.stringify(summary));
