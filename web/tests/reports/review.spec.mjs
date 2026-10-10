import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

async function open(page, context, name) {
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
  await page.addInitScript(() => {
    window.cspViolations = [];
    document.addEventListener('securitypolicyviolation', e => window.cspViolations.push(`${e.violatedDirective}: ${e.blockedURI}`));
  });
  await context.setOffline(true);
  await page.goto(pathToFileURL(join(process.env.ERRORBARS_REPORT_FIXTURES, `${name}.html`)).href);
  await expect(page.locator('#question-rows tr').first()).toBeVisible();
  return async () => {
    expect(errors).toEqual([]); expect(requests).toEqual([]);
    expect(await page.evaluate(() => window.cspViolations)).toEqual([]);
  };
}

async function download(page, name) {
  const waiting = page.waitForEvent('download');
  await page.getByRole('button', { name, exact: true }).click();
  const item = await waiting;
  return { name: item.suggestedFilename(), text: await readFile(await item.path(), 'utf8') };
}

test('real retained COPA runs expose their discordances, source records and unchanged complete JSON', async ({ page, context }) => {
  const clean = await open(page, context, 'copa');
  await expect(page.locator('#effect-value')).toHaveText('+0.2000');
  await expect(page.locator('#inference-description')).toContainText('Exact McNemar p = 0.2891');
  await expect(page.locator('#identity-note')).toContainText('20 matching');
  await expect(page.locator('#outcome-counts')).toHaveText('6A higher2B higher12equal0excluded (unpaired)');
  await page.getByLabel('Show questions').selectOption('b_higher');
  await expect(page.locator('#question-rows tr')).toHaveCount(2);
  const target = page.getByRole('button', { name: 'Inspect question copa-15', exact: true });
  await target.focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#inspector-heading')).toBeFocused();
  await expect(page.locator('#inspector')).toContainText('record 16 / line 16');
  await expect(page.locator('#inspector')).toContainText('Score: acc');
  await expect(page.locator('#inspector')).toContainText('Filter: none');
  await page.getByRole('button', { name: 'Back to question', exact: true }).press('Enter');
  await expect(target).toBeFocused();
  const exported = await download(page, 'Download evidence (JSON)');
  const data = JSON.parse(exported.text);
  expect(data.questions).toHaveLength(20); // The two-row filter must not lose eighteen questions.
  expect(data.comparison.mean_diff).toBe(0.2);
  expect(data.comparison.mcnemar).toMatchObject({ n01: 2, n10: 6 });
  expect(data.inference).toMatchObject({ test: 'mcnemar_exact', p_value: 0.2890625, ci_low: null, ci_high: null });
  expect(data.cohort.n_identity_matching).toBe(20);
  expect(data.questions.filter(q => q.difference === -1).map(q => q.question_id)).toEqual(['copa-15', 'copa-16']);
  expect(exported.text).not.toContain('The man turned on the faucet');
  expect(exported.text).not.toContain('/home/');
  expect(exported.name).toBe('errorbars-comparison.json');
  await clean();
});

test('two binary wins retain uncertainty in the headline and downloaded evidence', async ({ page, context }) => {
  const clean = await open(page, context, 'two-wins');
  await expect(page.locator('#inference-description')).toContainText('Exact McNemar p = 0.5000');
  await expect(page.locator('#inference-description')).toContainText('No significant difference detected');
  await expect(page.locator('.interval-table')).toContainText('Paired t (diagnostic)');
  await expect(page.locator('#interval-chart')).toContainText('t approx.');
  await expect(page.getByText('No exact mean-difference interval is supplied.', { exact: false })).toBeVisible();
  const data = JSON.parse((await download(page, 'Download evidence (JSON)')).text);
  expect(data.inference).toMatchObject({ test: 'mcnemar_exact', p_value: 0.5, confidence: null });
  expect(data.comparison.p_value).toBe(0); // Clearly separated legacy diagnostic.
  await page.setViewportSize({ width: 375, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await clean();
});

test('binary repeated-generation means are not advertised as exact Bernoulli trials', async ({ page, context }) => {
  const clean = await open(page, context, 'binary-repeats');
  await expect(page.locator('#inference-description')).toContainText('paired-t CI');
  await expect(page.locator('#inference-description')).not.toContainText('McNemar');
  const data = JSON.parse((await download(page, 'Download evidence (JSON)')).text);
  expect(data.inference).toMatchObject({ test: 'paired_t', mcnemar_applicable: false });
  expect(data.comparison.mcnemar).not.toBeNull(); // Preserved, ineligible diagnostic.
  await clean();
});

test('unequal cohorts, repeated generations, paging and filtered CSV stay separate from inference', async ({ page, context }) => {
  const clean = await open(page, context, 'partial');
  const before = await page.locator('#inference-description').textContent();
  await expect(page.locator('#question-rows tr')).toHaveCount(40);
  await page.getByRole('button', { name: 'Next questions', exact: true }).click();
  await expect(page.locator('#row-status')).toContainText('41-80 of 135');
  await page.getByRole('button', { name: 'Inspect excluded questions', exact: true }).click();
  await expect(page.locator('#question-rows tr')).toHaveCount(15);
  await page.getByRole('button', { name: 'Inspect question q000', exact: true }).click();
  await expect(page.locator('#inspector')).toContainText('Missing is not zero');
  const missing = await download(page, 'Download shown questions (CSV)');
  expect(missing.text.trim().split('\r\n')).toHaveLength(16);
  expect(missing.text).toContain('"q000","group-00","only_a"');
  await page.getByRole('button', { name: 'Reset filters', exact: true }).click();
  const all = await download(page, 'Download shown questions (CSV)');
  expect(all.text.trim().split('\r\n')).toHaveLength(136); // All pages, not just forty DOM rows.
  await page.getByLabel('Search question or cluster').fill('q005');
  await page.getByRole('button', { name: 'Inspect question q005', exact: true }).click();
  await expect(page.getByRole('region', { name: 'A observed generations' }).locator('tbody tr')).toHaveCount(25);
  await expect(page.locator('#draws-a')).toHaveText('1-25 of 151 draws');
  await page.getByRole('button', { name: 'Next A draws', exact: true }).click();
  await expect(page.locator('#draws-a')).toHaveText('26-50 of 151 draws');
  await expect(page.locator('#draws-a')).toBeFocused();
  const data = JSON.parse((await download(page, 'Download evidence (JSON)')).text);
  expect(data.cohort).toMatchObject({ n_shared: 120, n_only_a: 5, n_only_b: 10, n_observations_a: 275 });
  expect(data.questions.find(q => q.question_id === 'q005').observations_a).toHaveLength(151);
  await expect(page.locator('#inference-description')).toHaveText(before);
  await clean();
});

test('cluster deletion points back to its original questions without recomputing a test', async ({ page, context }) => {
  const clean = await open(page, context, 'clustered');
  const before = await page.locator('#inference-description').textContent();
  await expect(page.locator('#cluster-rows tr').first()).toContainText('passage-005');
  await expect(page.locator('#cluster-rows tr').first()).toContainText('+0.0513');
  await page.locator('#cluster-rows .cluster-link').first().focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#questions')).toBeFocused();
  await expect(page.locator('#cluster-filter')).toContainText('passage-005');
  await expect(page.locator('#question-rows tr')).toHaveCount(5);
  const csv = await download(page, 'Download shown questions (CSV)');
  expect(csv.text.trim().split('\r\n')).toHaveLength(6);
  await page.getByRole('button', { name: 'Clear cluster filter', exact: true }).click();
  await expect(page.locator('#search')).toBeFocused();
  await expect(page.locator('#row-status')).toContainText('of 200');
  await page.getByRole('button', { name: 'Next clusters', exact: true }).click();
  await expect(page.locator('#cluster-status')).toContainText('Page 2 of 4');
  await expect(page.locator('#inference-description')).toHaveText(before);
  await clean();
});

test('conflicting content is inspectable while the paired result is withheld', async ({ page, context }) => {
  const clean = await open(page, context, 'conflict');
  await expect(page.locator('#effect-value')).toHaveText('unavailable');
  await expect(page.locator('#inference-description')).toContainText('conflicting question content');
  await expect(page.locator('#identity-note')).toContainText('1 conflicting');
  await page.getByLabel('Show questions').selectOption('conflicting');
  await expect(page.locator('#question-rows tr')).toHaveCount(1);
  await page.getByRole('button', { name: 'Inspect question copa-0', exact: true }).click();
  await expect(page.locator('#inspector')).toContainText('withheld for the entire comparison');
  const data = JSON.parse((await download(page, 'Download evidence (JSON)')).text);
  expect(data.comparison).toBeNull(); expect(data.cohort.mean_difference).toBeNull();
  const question = data.questions.find(q => q.question_id === 'copa-0');
  expect(question.observations_a[0].question_hash).not.toBe(question.observations_b[0].question_hash);
  await clean();
});

test('scorer conflicts retain matching questions and export the changed grading evidence', async ({ page, context }) => {
  const clean = await open(page, context, 'scoring-conflict');
  await expect(page.locator('#effect-value')).toHaveText('unavailable');
  await expect(page.locator('#inference-description')).toContainText('conflicting scoring rules');
  await expect(page.locator('#identity-note')).toContainText('2 matching');
  await expect(page.locator('#scoring-note')).toContainText('2 conflicting');
  await page.getByLabel('Show questions').selectOption('conflicting');
  await expect(page.locator('#question-rows tr')).toHaveCount(2);
  await page.getByRole('button', { name: 'Inspect question q1', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#inspector-heading')).toBeFocused();
  await expect(page.locator('#inspector')).toContainText('Conflicting scoring rules');
  await expect(page.locator('#inspector')).toContainText('Question identity: matching');
  await expect(page.locator('#inspector')).not.toContainText('Conflicting question content');
  await page.getByRole('region', { name: 'A observed generations' })
    .getByText('Scorer configuration fingerprint', { exact: true }).click();
  await expect(page.getByRole('region', { name: 'A observed generations' })).toContainText('exact');
  const data = JSON.parse((await download(page, 'Download evidence (JSON)')).text);
  expect(data.comparison).toBeNull(); expect(data.inference).toBeNull();
  expect(data.cohort.n_identity_matching).toBe(2);
  expect(data.cohort.n_scoring_conflicting).toBe(2);
  const q = data.questions.find(q => q.question_id === 'q1');
  expect(q.scoring).toBe('conflicting'); expect(q.difference).toBeNull();
  expect(q.observations_a[0].scorer).toBe('inspect:match');
  expect(q.observations_a[0].scorer_config).not.toBe(q.observations_b[0].scorer_config);
  const csv = (await download(page, 'Download shown questions (CSV)')).text;
  expect(csv).toContain('"scoring"');
  expect(csv).toContain('"q1","","conflicting","matching","conflicting"');
  await clean();
});

test('hostile identifiers stay text, controls stay visible, CSV is inert and JSON preserves evidence', async ({ page, context }) => {
  const clean = await open(page, context, 'hostile');
  expect(await page.evaluate(() => window.pwned)).toBeUndefined();
  await expect(page.locator('script')).toHaveCount(2);
  await expect(page.locator('img')).toHaveCount(0);
  await expect(page.locator('.model-pair')).toContainText('\\u202e');
  await page.getByLabel('Search question or cluster').fill('SUM');
  const csv = (await download(page, 'Download shown questions (CSV)')).text;
  expect(csv).toContain('"\'=SUM(1,2)"');
  const raw = JSON.parse((await download(page, 'Download evidence (JSON)')).text);
  expect(raw.questions.some(q => q.question_id === '=SUM(1,2)')).toBe(true);
  expect(raw.model_a).toContain('</script><script>');
  await page.getByLabel('Search question or cluster').fill('no-such-question');
  await expect(page.locator('#no-questions')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download shown questions (CSV)' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Download evidence (JSON)' })).toBeEnabled();
  await page.getByRole('button', { name: 'Reset filters', exact: true }).click();
  await expect(page.locator('#question-rows tr')).toHaveCount(5);
  await clean();
});

test('an empty intersection keeps observations and never invents a zero difference', async ({ page, context }) => {
  const clean = await open(page, context, 'missing');
  await expect(page.locator('#effect-value')).toHaveText('unavailable');
  await expect(page.locator('#difference-chart')).toContainText('No comparable question differences');
  await page.getByRole('button', { name: 'Inspect shared questions', exact: true }).click();
  await expect(page.locator('#no-questions')).toBeVisible();
  const data = JSON.parse((await download(page, 'Download evidence (JSON)')).text);
  expect(data.comparison).toBeNull(); expect(data.questions).toHaveLength(4);
  expect(data.questions.every(q => q.difference === null)).toBe(true);
  await clean();
});

test('large evidence stays complete while DOM rows and interaction remain bounded', async ({ page, context }) => {
  const clean = await open(page, context, 'large');
  await expect(page.locator('#question-rows tr')).toHaveCount(40);
  await expect(page.locator('#row-status')).toContainText('12,000 matching');
  await page.getByLabel('Search question or cluster').fill('question-11999');
  await expect(page.locator('#question-rows tr')).toHaveCount(1);
  await page.getByRole('button', { name: 'Inspect question question-11999', exact: true }).click();
  await expect(page.locator('#inspector')).toContainText('Source location unavailable');
  const data = JSON.parse((await download(page, 'Download evidence (JSON)')).text);
  expect(data.questions).toHaveLength(12000);
  expect(data.questions.at(-1).question_id).toBe('question-11999');
  await expect(page.locator('.evidence-layout tbody tr')).toHaveCount(3);
  await clean();
});

for (const viewport of [{ width: 1440, height: 1000 }, { width: 375, height: 850 }, { width: 320, height: 800 }]) {
  test(`light and dark accessibility, navigation and print at ${viewport.width}px`, async ({ page, context }) => {
    await page.setViewportSize(viewport); await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    const clean = await open(page, context, 'copa');
    for (const theme of ['light', 'dark']) {
      if (theme === 'dark') await page.getByRole('button', { name: 'Use dark theme' }).click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
      await page.getByRole('button', { name: 'Inspect question copa-15', exact: true }).click();
      await expect(page.locator('#inspector-heading')).toBeFocused();
      await page.getByRole('button', { name: 'Back to question', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Inspect question copa-15', exact: true })).toBeFocused();
    }
    await page.emulateMedia({ media: 'print' });
    await expect(page.getByRole('button', { name: 'Download evidence (JSON)' })).toBeHidden();
    await expect(page.locator('#effect-value')).toBeVisible();
    expect(await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor)).toBe('rgb(255, 255, 255)');
    const notice = await page.locator('#print-note').evaluate(el => getComputedStyle(el, '::after').content);
    expect(notice).toContain('current pages only');
    await clean();
  });
}

test('printing follows the paper palette when dark mode comes only from the system', async ({ page, context }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  const clean = await open(page, context, 'copa');
  await expect(page.getByRole('button', { name: 'Use light theme' })).toBeVisible();
  expect(await page.locator('html').getAttribute('data-theme')).toBeNull();
  await page.emulateMedia({ media: 'print' });
  expect(await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor)).toBe('rgb(255, 255, 255)');
  await clean();
});
