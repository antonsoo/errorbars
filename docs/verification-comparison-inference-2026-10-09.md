# Comparison inference verification - 2026-10-09

Implementation: `f7644a2`. A reproduced two-question report previously
headlined p=0 while retaining exact McNemar p=0.5. It now selects the exact
binary test and labels its paired-t interval as a diagnostic approximation.
The same selection rule is shared with leaderboards; repeated-generation means
and grouped questions keep their appropriate methods.

## Independent evidence

- All 14,878 pairs from the retained 173-submission SWE-bench snapshot were
  checked against SciPy's two-sided binomial test, with counts derived directly
  from integer outcome masks. Maximum absolute error: 1.44e-15.
- 102 single task-independent decisions at alpha=0.05 differ between the
  previous paired-t headline and the exact test. These are unadjusted pair
  decisions, distinct from the Holm-corrected leaderboard display audit.
- Native COPA log records independently give 6 A-only and 2 B-only wins, hence
  exact p=0.2890625. The installed CLI, generated HTML and downloaded evidence
  all select that result; p=0.16255 remains a labeled paired-t diagnostic.
- Four installed workflows cover the real logs, two binary wins, repeated
  binary-looking question means, and a clustered comparison. JSON and HTML
  agree on method, p-value, interval availability and applicability of McNemar.

[Replay and all results](../studies/comparison-inference/README.md).

## Checks and artifacts

Source: Python 3.12.12, NumPy 2.5.3, SciPy 1.18.1. Ruff and mypy pass;
**550 Python tests pass**. The same committed source was exported to the
separate archive environment used earlier in this session, with locked Python
3.14 dependencies: lint, type checking and all 550 tests pass there too.

The built wheel was installed with no dependencies into the existing isolated
Python 3.10.21 / NumPy 1.24.0 environment. Four actual CLI/HTML replays and
**26 offline Chromium/Firefox report workflows** pass, including downloaded
JSON, real keyboard navigation, accessibility, narrow screens and printing.
The report's interval chart also labels the t approximation and exposes that
distinction to assistive technology.

The production site was rebuilt on Node 24.21.0: lint, type checking,
**685 formula checks**, and **42 Chromium/Firefox browser workflows** pass.
Those checks were repeated from the committed source in the separate archive;
the resulting static bundle is byte-identical to the working-checkout build.
The actual 40-vs-24 discordance example now shows exact p=0.0599412, with the
previous t approximation p=0.0453913 identified separately. Swapping A/B keeps
the decision and reverses the signed gap.

Additional installed-report and production-page captures were checked at
1440 and 375 pixels in both engines. The actual screenshots were opened and
visually inspected. No screenshot is a mockup. Their text and measured
no-overflow assertions are retained in the study's browser record.

## Scope

No exact mean-difference interval is implemented for McNemar; the selected
inference explicitly exports null endpoints and confidence. Original numeric
comparison diagnostics remain backward compatible. Original SWE-bench study
figures remain paired-t analyses and are labeled accordingly. A non-significant
result does not establish equivalence. No new model inference was performed.

GitHub Actions is disabled on this repository. Local checks above therefore
provide the validation record; a source push is not a CI run or PyPI release.

## Published source and hosted verification

Source was pushed through `f36cbd4`. The byte-identical verified static build
was committed on the existing `gh-pages` history as `70fecf1` and pushed
normally (no force push). GitHub's live HTML serves the expected
`swe-bench-BkK202lq.js` asset and the exact-test explanation. All 42 browser
workflows also passed against `https://antonsoo.github.io/errorbars/`, in both
Chromium and Firefox. This includes the actual 40-vs-24 counterexample,
swapping/linking submissions, local pasted runs, narrow layouts and accessibility.
GitHub Actions remained disabled; no PyPI release was made.
