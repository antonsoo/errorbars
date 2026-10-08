import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function boot(page, query = '') {
  const siteOrigin = new URL(test.info().project.use.baseURL).origin;
  const errors = [];
  const external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== siteOrigin) external.push(request.url());
  });
  await page.addInitScript(() => {
    window.cspViolations = [];
    document.addEventListener('securitypolicyviolation', e => window.cspViolations.push(`${e.violatedDirective}: ${e.blockedURI}`));
  });
  await page.goto(`./swe-bench.html${query}`);
  await expect(page.locator('#verdict')).not.toBeEmpty();
  return async () => {
    expect(errors).toEqual([]);
    expect(external).toEqual([]);
    expect(await page.evaluate(() => window.cspViolations)).toEqual([]);
  };
}

const row = (page, name) => page.locator('#result-table tr', { has: page.getByRole('rowheader', { name, exact: true }) }).locator('td');

test('the default pair differs on tasks and not across repositories', async ({ page }) => {
  const clean = await boot(page);
  await expect(page.locator('#submission-count')).toHaveText('173');
  await expect(page.locator('#verdict')).toHaveText('Different on tasks like these.');
  await expect(page.locator('#verdict-detail')).toContainText('Claude 4.5 Opus (high) is 4.0 points ahead of GPT 5.2 (high)');
  // The same numbers `errorbars compare` prints for this pair (studies/swe-bench-verified/README.md).
  await expect(row(page, 'Gap, A minus B')).toHaveText('+4.0 points');
  await expect(row(page, 'Tasks as the sample')).toContainText('+1.0 to +7.0');
  await expect(row(page, 'Tasks as the sample')).toContainText('0.010');
  await expect(row(page, 'Repositories as the sample')).toContainText('−3.7 to +11.7');
  await expect(row(page, 'Repositories as the sample')).toContainText('3.3 degrees of freedom from 12 repositories');
  await expect(row(page, 'Tasks where they differ')).toContainText('60: only A resolved 40, only B resolved 20');
  await expect(page.locator('#task-grid .cell')).toHaveCount(500);
  await expect(page.locator('#task-grid .cell-a')).toHaveCount(40);
  await expect(page.locator('#task-grid .cell-b')).toHaveCount(20);
  await expect(page.locator('#task-grid .repo').first()).toContainText('django/django');
  await expect(page.locator('#task-grid .repo').first()).toContainText('231 tasks');
  await clean();
});

test('choosing, swapping and linking a pair', async ({ page }) => {
  const clean = await boot(page);
  await page.getByLabel('A', { exact: true }).selectOption('20251205_sonar-foundation-agent_claude-opus-4-5');
  await page.getByLabel('B', { exact: true }).selectOption('20251127_openhands_claude-opus-4-5');
  await expect(page.locator('#verdict')).toHaveText('Not distinguishable.');
  await expect(row(page, 'Gap, A minus B')).toHaveText('+1.6 points');
  await expect(page).toHaveURL(/a=20251205_sonar-foundation-agent_claude-opus-4-5&b=20251127_openhands_claude-opus-4-5/);

  await page.getByRole('button', { name: 'Swap A and B' }).click();
  await expect(row(page, 'Gap, A minus B')).toHaveText('−1.6 points');
  await expect(page.locator('#verdict-detail')).toContainText('Sonar Foundation Agent + Claude 4.5 Opus is 1.6 points ahead');

  await page.reload();
  await expect(row(page, 'Gap, A minus B')).toHaveText('−1.6 points');

  await page.getByLabel('B', { exact: true }).selectOption('20251127_openhands_claude-opus-4-5');
  await expect(page.locator('#verdict')).toHaveText('Pick two different submissions.');
  await clean();
});

test('a far-apart pair is different across repositories too', async ({ page }) => {
  const clean = await boot(page, '?a=20251205_sonar-foundation-agent_claude-opus-4-5&b=20240402_sweagent_gpt4');
  await expect(page.locator('#verdict')).toHaveText('Different, on these tasks and across repositories.');
  await clean();
});

test('a pasted run is compared and bad input is refused', async ({ page }) => {
  const clean = await boot(page);
  await page.getByText('Use a run of my own as A').click();
  const box = page.getByLabel('Resolved task ids, one per line, or the report the SWE-bench harness writes');

  await page.getByRole('button', { name: 'Compare this run' }).click();
  await expect(page.locator('#own-status')).toHaveText('Paste the resolved task ids first.');

  await box.fill('django__django-11099\nnot-a-task-1\n<img src=x onerror=alert(1)>');
  await page.getByRole('button', { name: 'Compare this run' }).click();
  // The markup splits on its spaces into three more unknown ids; none of it becomes an element.
  await expect(page.locator('#own-status')).toContainText('4 of these are not SWE-bench Verified task ids (first: not-a-task-1)');
  await expect(page.locator('#own-status img')).toHaveCount(0);
  await expect(page.locator('#verdict')).toHaveText('Different on tasks like these.');

  await box.fill('{"resolved_ids": ["django__django-11099", "sympy__sympy-20590", "astropy__astropy-12907"]}');
  await page.getByLabel('Name', { exact: true }).fill('<b>mine</b>');
  await page.getByRole('button', { name: 'Compare this run' }).click();
  await expect(page.locator('#own-status')).toContainText('3 of 500 tasks resolved (0.6%)');
  await expect(row(page, 'Resolved')).toContainText('A 0.6% (3 of 500)');
  await expect(row(page, 'Source')).toContainText('A your own');
  await expect(page.locator('#verdict-detail')).toContainText('ahead of <b>mine</b>');
  await expect(page.locator('#verdict-detail b')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Swap A and B' })).toBeDisabled();

  await page.getByRole('button', { name: 'Remove it' }).click();
  await expect(row(page, 'Resolved')).toContainText('A 76.8% (384 of 500)');
  await clean();
});

for (const theme of ['light', 'dark']) {
  test(`no accessibility findings, ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    const clean = await boot(page);
    await page.getByText('Use a run of my own as A').click();
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']).analyze();
    expect(results.violations.map(v => `${v.id}: ${v.nodes.length}`)).toEqual([]);
    await clean();
  });
}

test('reflows at phone width without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  const clean = await boot(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  await clean();
});
