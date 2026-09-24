# Changelog

All notable changes to this project are documented in this file.

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
