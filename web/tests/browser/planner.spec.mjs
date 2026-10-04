import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';

async function boot(page) {
  const errors = [];
  const external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== 'http://127.0.0.1:4197') external.push(request.url());
  });
  await page.addInitScript(() => {
    window.cspViolations = [];
    document.addEventListener('securitypolicyviolation', e => window.cspViolations.push(`${e.violatedDirective}: ${e.blockedURI}`));
  });
  await page.goto('./');
  await expect(page.locator('#result-n')).toHaveText('3,053');
  return async () => {
    expect(errors).toEqual([]);
    expect(external).toEqual([]);
    expect(await page.evaluate(() => window.cspViolations)).toEqual([]);
  };
}

async function downloadPlan(page) {
  const waiting = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download plan (JSON)' }).click();
  const download = await waiting;
  expect(download.suggestedFilename()).toBe('errorbars-plan.json');
  return JSON.parse(await readFile(await download.path(), 'utf8'));
}

test('exact editing, slider controls, and both directions preserve assumptions', async ({ page }) => {
  const clean = await boot(page);
  await page.getByLabel('Baseline accuracy (%)', { exact: true }).fill('65.4321');
  await page.getByLabel('Paired correlation', { exact: true }).fill('0.123456');
  await page.getByLabel('Average cluster size', { exact: true }).fill('3.5');
  await page.getByLabel('Intraclass correlation (ICC)', { exact: true }).fill('0.2');
  const p = await downloadPlan(page);
  expect(p.format).toBe('errorbars-plan');
  expect(p.schemaVersion).toBe(1);
  expect(p.inputs.baselineAccuracy).toBe(0.654321);
  expect(p.inputs.rho).toBe(0.123456);
  expect(p.inputs.clusterDesignEffect).toBe(1.5);
  expect(p.result.modelAnswers).toBe(p.result.nQuestions * 2);
  expect(p.units.difference).toContain('fraction');
  expect(p.assumptions).toHaveLength(5);
  expect(p.cliCommand).toContain('--rho 0.123456');
  await page.getByRole('radio', { name: 'Gap my budget can detect' }).check();
  await page.getByLabel('Available questions', { exact: true }).fill(String(p.result.nQuestions));
  const inverse = await downloadPlan(page);
  expect(inverse.result.minimumDetectableEffect).toBeLessThanOrEqual(0.03);
  expect(inverse.inputs.targetDifference).toBeNull();
  expect(inverse.cliCommand).toContain(`--n ${p.result.nQuestions}`);
  expect(inverse.inputs.baselineAccuracy).toBe(p.inputs.baselineAccuracy);
  await page.getByLabel('Adjust paired correlation', { exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#rho')).toHaveValue('0.13');
  await expect(page.locator('#rho-range')).toBeFocused();
  await clean();
});

test('invalid edits remove the result and disable downloads until corrected', async ({ page }) => {
  const clean = await boot(page);
  const input = page.getByLabel('Gap to detect (percentage points)', { exact: true });
  for (const value of ['', '-1', '51']) {
    await input.fill(value);
    await expect(page.locator('#input-error')).toBeVisible();
    await expect(input).toHaveAttribute('aria-invalid', 'true');
    await expect(page.locator('#plan-output')).toBeHidden();
    await expect(page.getByRole('button', { name: 'Download plan (JSON)' })).toBeDisabled();
    await expect(input).toBeFocused();
  }
  await page.getByRole('radio', { name: 'Gap my budget can detect' }).check();
  await expect(page.locator('#plan-output')).toBeVisible();
  await expect(page.locator('#delta-control')).toBeHidden();
  await page.getByLabel('Available questions', { exact: true }).fill('2.5');
  await expect(page.locator('#input-error')).toContainText('whole number');
  await page.getByLabel('Available questions', { exact: true }).fill('500');
  await expect(page.locator('#plan-output')).toBeVisible();
  await page.getByRole('radio', { name: 'Questions needed', exact: true }).check();
  await expect(page.locator('#plan-output')).toBeHidden();
  await input.fill('3');
  await expect(page.locator('#result-n')).toHaveText('3,053');
  await clean();
});

test('impossible accuracy improvements and small group counts remain explicit', async ({ page }) => {
  const clean = await boot(page);
  await page.locator('#baseline').fill('99');
  await expect(page.locator('#input-error')).toContainText('exceeds 100%');
  await expect(page.locator('#delta')).toHaveValue('3');
  await page.getByRole('radio', { name: 'Gap my budget can detect' }).check();
  await page.locator('#budget').fill('20');
  await page.locator('#clusterSize').fill('10');
  await page.locator('#icc').fill('0.2');
  await expect(page.locator('#plan-warnings')).toContainText('cannot detect an achievable');
  await expect(page.locator('#plan-warnings')).toContainText('Fewer than 30 groups');
  const p = await downloadPlan(page);
  expect(p.result.achievableImprovement).toBe(false);
  expect(p.result.approximateGroups).toBe(2);
  expect(p.warnings).toHaveLength(3);
  await clean();
});

test('two-question chart marker stays inside its plot and only computed points appear', async ({ page }) => {
  const clean = await boot(page);
  await page.locator('#delta').fill('50');
  await page.locator('#rho').fill('0.95');
  await page.locator('#power').fill('50');
  await page.locator('#alpha').fill('20');
  await expect(page.locator('#result-n')).toHaveText('2');
  const marker = page.locator('.chart-marker');
  expect(Number(await marker.getAttribute('cx'))).toBeGreaterThanOrEqual(46);
  expect(Number(await marker.getAttribute('cx'))).toBeLessThanOrEqual(542);
  expect(Number(await marker.getAttribute('cy'))).toBeGreaterThanOrEqual(14);
  expect(Number(await marker.getAttribute('cy'))).toBeLessThanOrEqual(250);
  await expect(page.locator('#chart circle')).toHaveCount(1);
  await expect(page.locator('#budget-rows tr.current-budget')).toContainText('2 (current)');
  await expect(page.locator('.chart-curve')).toHaveCSS('animation-name', 'none');
  const p = await downloadPlan(page);
  const [, gap] = await page.locator('#budget-rows tr.current-budget td').allTextContents();
  expect(gap).toContain((p.result.minimumDetectableEffect * 100).toFixed(3));
  await clean();
});

test('reset and CLI selection work with keyboard, without clipboard permissions', async ({ page }) => {
  const clean = await boot(page);
  await page.getByText('Reproduce this plan', { exact: true }).click();
  await page.getByRole('button', { name: 'Select command' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#cli-command')).toBeFocused();
  expect(await page.locator('#cli-command').evaluate(el => el.selectionEnd - el.selectionStart)).toBeGreaterThan(100);
  await page.getByRole('radio', { name: 'Gap my budget can detect' }).check();
  await page.locator('#budget').fill('');
  await page.getByRole('button', { name: 'Reset plan' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('radio', { name: 'Questions needed', exact: true })).toBeChecked();
  await expect(page.locator('#result-n')).toHaveText('3,053');
  await expect(page.getByRole('button', { name: 'Reset plan' })).toBeFocused();
  await expect(page.locator('#action-status')).toHaveText('Default plan restored.');
  await clean();
});

test('blocked storage, offline calculations and downloads remain usable', async ({ page, context }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new Error('storage blocked'); } });
  });
  const clean = await boot(page);
  await context.setOffline(true);
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await page.getByRole('radio', { name: 'Gap my budget can detect' }).check();
  await page.locator('#budget').fill('1000');
  expect((await downloadPlan(page)).result.nQuestions).toBe(1000);
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await clean();
});

for (const theme of ['light', 'dark']) {
  for (const width of [1440, 375]) {
    test(`${theme} at ${width}px: accessible controls, readable results, no overflow`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      const clean = await boot(page);
      for (const mode of ['questions', 'budget']) {
        if (mode === 'budget') {
          await page.getByRole('radio', { name: 'Gap my budget can detect' }).check();
          await page.locator('#budget').fill('20');
          await page.getByText('Reproduce this plan', { exact: true }).click();
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const audit = await new AxeBuilder({ page }).analyze();
        expect(audit.violations).toEqual([]);
      }
      await clean();
    });
  }
}

test('mobile result link follows errors and returns to a complete result', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  const clean = await boot(page);
  const link = page.locator('#mobile-result');
  await expect(link).toHaveText('View plan: 3,053 questions per model');
  await page.locator('#alpha').fill('');
  await expect(link).toHaveText('Fix input: Significance level (%)');
  await link.click();
  await expect(page.locator('#alpha')).toBeFocused();
  await page.locator('#alpha').fill('5');
  await link.click();
  await expect(page.locator('#plan-output')).toBeFocused();
  await expect(page.locator('#result-n')).toBeInViewport();
  await clean();
});

test('extreme supported plans retain finite results and fit a narrow screen', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  const clean = await boot(page);
  for (const [key, value] of Object.entries({ delta: '0.01', rho: '-0.95', clusterSize: '1000', icc: '1', alpha: '0.1', power: '99.9' })) {
    await page.locator(`#${key}`).fill(value);
  }
  const p = await downloadPlan(page);
  expect(Number.isSafeInteger(p.result.nQuestions)).toBe(true);
  expect(Number.isFinite(p.result.minimumDetectableEffect)).toBe(true);
  expect(p.result.minimumDetectableEffect).toBeLessThanOrEqual(0.0001);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.locator('#chart svg').innerHTML()).not.toMatch(/NaN|Infinity/);
  await clean();
});


test('chart labels keep their size when the viewport changes', async ({ page }) => {
  const clean = await boot(page);
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect.poll(async () => page.locator('#chart').evaluate(el => {
      const svg = el.querySelector('svg');
      return Math.abs(svg.viewBox.baseVal.width - el.clientWidth);
    })).toBeLessThanOrEqual(1);
  }
  await clean();
});
