# Changelog

All notable changes to this project are documented in this file.

## [0.1.1] - 2026-09-30

### Fixed

- A non-finite score (`nan`, `inf`) was accepted and propagated into every
  mean, CI and p-value; on a leaderboard the NaN model sorted to rank 1.
  Loading now fails with the row number.
- A repeated (model, question, sample) row was counted as another question,
  inflating n and shrinking standard errors. Loading now fails with both row
  numbers and says to give repeated generations distinct `sample` values.
- `power` answered "2 questions" for a baseline of 0 or 1 (where p(1-p) = 0)
  and accepted targets above 100% (`--baseline 0.98 --delta 0.05`). The
  baseline must be strictly between 0 and 1, baseline + delta can't exceed
  1, and a continuous-metric variance must be positive; the web calculator's
  effect-size slider is capped at 1 - baseline to match.
- `compare`/`summarize` with an unknown model name said "fewer than 2 shared
  question_ids" or "no rows"; they now name the missing model and list the
  models in the file.
- Install hints for the optional extras named `errorbars` on PyPI, where it
  isn't published; they now name the dependency or the Git URL.

## [0.1.0] - 2026-09-24

Initial release.

- `summarize`: CLT, Wilson, and bootstrap confidence intervals; clustered
  standard errors with design effect and ICC; within/between-question
  variance decomposition for repeated samples.
- `compare`: paired mean difference, SE, CI, p-value; correlation and
  variance reduction from pairing; clustered paired SE; exact McNemar test
  for binary scores.
- `leaderboard`: per-model CIs, Holm-corrected pairwise paired tests,
  maximal-clique grouping of statistically indistinguishable models, SVG and
  (optional) matplotlib forest plots.
- `power`: questions needed for a target effect/power, and minimum
  detectable effect for a given n, accounting for pairing correlation,
  repeated sampling, and cluster design effect.
- CLI (`errorbars summarize|compare|leaderboard|power|import`) with `rich`
  tables and `--json` output.
- Adapters: `errorbars import lm-eval|inspect` converts
  lm-evaluation-harness `--log_samples` JSONL or an Inspect AI `.eval` log
  into the canonical format, verified against real output from lm-eval
  0.4.13 and inspect-ai 0.3.268.
- Web calculator (Vite + TypeScript) mirroring the Python power formulas,
  with shared JSON test vectors.
