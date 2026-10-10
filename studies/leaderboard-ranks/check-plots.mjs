// Inspect actual exported SVGs from disk, including every text element on a 173-model board.
// node studies/leaderboard-ranks/check-plots.mjs ARTIFACT_DIRECTORY
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox } from '../../web/node_modules/playwright/index.mjs';

const directory = resolve(process.argv[2]);
await mkdir(directory, { recursive: true });
const results = [];
for (const [engine, browserType] of Object.entries({ chromium, firefox })) {
  const browser = await browserType.launch();
  try {
    const context = await browser.newContext({ viewport: { width: 640, height: 860 }, offline: true });
    const page = await context.newPage();
    for (const name of ['task-independent-before', 'task-independent-after', 'repository-clustered-after', 'gaps']) {
      await page.goto(pathToFileURL(join(directory, `${name}.svg`)).href);
      const measured = await page.evaluate(() => {
        const svg = document.documentElement, view = svg.viewBox.baseVal;
        const texts = [...document.querySelectorAll('text')];
        const clipped = texts.filter(text => {
          const b = text.getBBox();
          return b.x < 0 || b.y < 0 || b.x + b.width > view.width || b.y + b.height > view.height;
        });
        const rows = [...document.querySelectorAll('.model-row')];
        const overlap = rows.slice(1).filter((row, index) => {
          const current = row.getBBox(), previous = rows[index].getBBox();
          return current.y < previous.y + previous.height;
        });
        return { width: view.width, height: view.height, texts: texts.length, clipped: clipped.length,
          rows: rows.length, overlappingRows: overlap.length };
      });
      if (name.endsWith('-after') || name === 'gaps') {
        assert.equal(measured.clipped, 0, `${engine} ${name}: clipped labels`);
        assert.equal(measured.overlappingRows, 0, `${engine} ${name}: overlapping rows`);
        assert.equal(measured.rows, name === 'gaps' ? 5 : 173);
      } else {
        assert.ok(measured.clipped > 0, 'baseline should reproduce clipped labels');
      }
      const clip = { x: 0, y: 0, width: measured.width, height: Math.min(measured.height, 860) };
      await page.screenshot({ path: join(directory, `${name}-${engine}.png`), clip });
      results.push({ engine, name, ...measured });
    }
    await context.close();
  } finally {
    await browser.close();
  }
}
await writeFile(join(directory, 'browsers.json'), `${JSON.stringify(results, null, 2)}\n`);
console.log(JSON.stringify(results, null, 2));
