# Leaderboard rank evidence verification - 2026-10-09

Implementation: `1eb377e`. The change repairs displayed conclusions while
preserving statistical results. The retained public-data audit compares
against baseline `6af9d95` on all 14,878 pairs in each of two scenarios.

- Task-independent SWE-bench board: prior rank spans imply 150 false directed
  ties across 77 models; exact rank sets imply zero.
- Repository-clustered board: zero before and after. Its earlier CLI used
  group letters, not the faulty span representation.
- Every original entry, pairwise result, group and alpha is exactly unchanged
  against the baseline implementation in the same environment.
- The synthetic five-model counterexample retains both a significant hole
  and an untested hole between non-significant ranks. JSON includes untested
  reasons and shared counts, and all three exports preserve cohort warnings.

[Audit and replay commands](../studies/leaderboard-ranks/README.md),
[full compact results](../studies/leaderboard-ranks/results.json),
[browser measurements](../studies/leaderboard-ranks/browsers.json), and
[installed-wheel results](../studies/leaderboard-ranks/installed.json).

## Local checks

Python 3.12.12, NumPy 2.5.3, SciPy 1.18.1:

```sh
.venv/bin/ruff check .
.venv/bin/mypy src/errorbars
.venv/bin/pytest -q
uv build
```

Ruff and mypy passed; 542 Python tests passed. The independently installed
wheel ran on Python 3.10.21 with NumPy 1.24.0 and no optional dependencies.
Its plain-text counterexample was checked directly, and both complete
public-board replays preserved all decisions and reproduced every SVG byte.
The first combined replay process terminated after the first two scenarios;
the scenarios were then run separately to completion, with per-scenario
results retained before combining the record.

The committed source was also exported into the clean archive used for the
previous repeat-planning verification, with its separate locked Python 3.14
environment, and lint, type checking and the full suite were repeated there.
The web bundle is unchanged by this repair; its 685 formula checks, production
build, 40 Chromium/Firefox page workflows and 22 installed-wheel report
workflows were checked earlier in this same working session, as recorded in
[the repeat-planning verification](verification-repeated-planning-2026-10-09.md).

## Export inspection

Actual standalone SVG files were opened with networking disabled in Chromium
and Firefox. Every text bounding box and every adjacent model-row bounding box
was measured across the complete 173-row exports, not only the screenshot
viewport. The previous independent-task SVG clipped 228 labels in Chromium
and 195 in Firefox. Both corrected public-board exports have zero clipped
labels and zero overlapping rows in either engine. Captures of the old/new
board and the five-model counterexample were opened and visually inspected.

These checks establish correctness for the retained boards and counterexample,
not a universal guarantee for every font or arbitrary input string. A
non-significant comparison does not establish equivalence, and marginal model
intervals are not paired-difference intervals. Source pushes do not release a
new PyPI package.
