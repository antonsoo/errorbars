# Table import integrity verification

The change refuses ambiguous DataFrame columns before pandas can discard values,
rejects malformed quoted CSV records, and reports parser errors with their physical
line. In the constructed duplicate-score case, choosing the last column reversed
A - B from +0.2 to -0.2. The corrected import refuses to choose for the caller.

Implementation: `482a1d41f54e24a0970f6b39bed78e1b251f4469`.
Baseline: `211611faf3bb66ec24688a43b66a27ea3e1a9a8d`.
[Reproduction, scripts, retained results and boundaries](../studies/table-imports/README.md).

| Actual workflow | Result |
| --- | --- |
| Duplicate DataFrame columns | 8/8 rejected before conversion, without a warning or input mutation; baseline 0/8 |
| Malformed CSV library imports | 12/12 located ValueErrors; baseline 0/12 |
| CLI summarize, compare, leaderboard and import | 48/48 located failures, exit 1, no traceback/stdout, existing output files intact; baseline 0/48 |
| Valid dialect variants | 48/48 unchanged full records and physical source locations |
| Valid DataFrames | 3/3 unchanged, including duplicate row indexes and custom columns |
| Retained CSV inputs | All 1,557 records across seven examples/studies unchanged |
| Retained public SWE-bench input | 1,000 records from two submissions unchanged; source pin and IDs retained |
| Actual valid CLI outputs | JSON and standalone HTML byte-identical before/after and in both wheel installations |

The malformed baseline cases include six accepted library imports and 18 CLI
commands that replaced existing files. Remaining malformed cases already failed;
the new behavior gives a located parser error instead of a different validation
failure or an uncaught CSV exception.

## Clean archive and installed artifact

A fresh archive of the implementation commit was installed with the frozen lockfile
on Python 3.12.12. Ruff, strict mypy across all 18 source files, and **627 tests**
passed. `uv build` created the sdist, then built the wheel from that sdist.
All **407 tracked archive files** matched the implementation checkout.

The wheel was installed in separate environments, outside the checkout:

| Runtime | Dependencies | Result |
| --- | --- | --- |
| Python 3.10.21 | NumPy 1.24.0, pandas 1.5.0, Rich 13.0.0 | Complete replay, 47 import tests, real installed `errorbars` entry point |
| Python 3.14.7 | NumPy 2.5.4, pandas 3.0.6 | Same workflows and results |

All **26 package files** match the source, clean archive, sdist, wheel and both
installations. Full record hashes, valid CLI JSON and generated HTML agree across
both installed runtimes. Artifact sizes and SHA-256 hashes are in the
[package receipt](../studies/table-imports/results/package.json). Version **0.2.4**
is unchanged; these are local verification artifacts, not a package release.

## Offline report checks

The real CLI-generated HTML was opened from disk with networking disabled in
Chromium and Firefox, at 375 and 1440 pixels. All four workflows inspected original
multiline source locations, filtered eight questions, downloaded the complete
40-question JSON and the eight-row CSV, and reported no page errors, HTTP requests
or horizontal overflow. Downloaded CSVs were independently parsed in Python and
checked against the expected question IDs. All four retained screenshots were
visually inspected. The installed wheels generate exactly the same HTML bytes.

The existing **28 report-browser workflows** also pass from the clean archive's
browser checkout, using the source environment's Python (whose package files match
the clean archive). They cover accessibility, phone layout, keyboard navigation,
scoring/identity conflicts, exports and large reports. The separate web demo has no
CSV input path and was not modified or deployed.

These checks do not prove source-dataset completeness. Entire missing records and
truncated unquoted values can still be valid CSV. The CSV parser retains Python's
existing dialect behavior for bare quotes in unquoted fields. Duplicate row indexes
are valid; duplicate DataFrame columns must be selected or renamed explicitly.
