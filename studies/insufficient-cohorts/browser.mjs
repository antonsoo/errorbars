// Inspect the actual standalone SVG exports with cached browsers, offline.
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../../web/package.json', import.meta.url));
const { chromium, firefox } = require('@playwright/test');
const records = [];
for (const [name, engine] of Object.entries({ chromium, firefox })) {
  const browser = await engine.launch();
  try {
    for (const file of ['partial', 'all-descriptive']) {
      const context = await browser.newContext({ viewport: { width: 1000, height: 800 } });
      await context.setOffline(true);
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(String(e)));
      await page.goto(new URL(`results/${file}.svg`, import.meta.url).href);
      await page.evaluate(() => document.fonts.ready);
      const result = await page.evaluate(() => {
        const svg = document.querySelector('svg');
        const { width, height } = svg.viewBox.baseVal;
        const texts = [...document.querySelectorAll('text')];
        return {
          width, height, texts: texts.length,
          outside: texts.filter(t => {
            const b = t.getBBox();
            return b.x < -0.5 || b.y < -0.5 || b.x + b.width > width + 0.5 || b.y + b.height > height + 0.5;
          }).map(t => t.textContent),
          unavailable: texts.filter(t => t.textContent === 'CI unavailable').length,
          annotationOutsidePlot: texts.filter(t => t.textContent === 'CI unavailable').filter(t => {
            const b = t.getBBox();
            return b.x < width * 0.34 || b.x + b.width > width * 0.70;
          }).map(t => t.textContent),
          openPoints: [...document.querySelectorAll('.model-row circle')]
            .filter(c => c.getAttribute('fill') === '#ffffff').length,
        };
      });
      const expected = file === 'partial' ? 1 : 2;
      if (errors.length || result.outside.length || result.annotationOutsidePlot.length ||
          result.unavailable !== expected || result.openPoints !== expected) {
        throw new Error(JSON.stringify({ name, file, errors, result }));
      }
      await page.locator('svg').screenshot({
        path: fileURLToPath(new URL(`../../docs/assets/insufficient-${file}-${name}.png`, import.meta.url)),
      });
      records.push({ browser: name, file, offline: true, ...result, errors });
      await context.close();
    }
  } finally {
    await browser.close();
  }
}
writeFileSync(new URL('results/rendering.json', import.meta.url), JSON.stringify(records, null, 2) + '\n');
console.log(JSON.stringify(records));
