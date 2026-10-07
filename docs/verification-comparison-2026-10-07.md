# Comparison evidence verification - 2026-10-07

This work adds an inspectable comparison workflow to Errorbars and fixes a
question-identity failure found while building it. Everything is local and
unreleased. No source push, Pages deployment or registry publication occurred.

## What changed in actual use

`errorbars compare ... --html comparison.html` now produces a portable report
that opens directly from disk. It shows the shared cohort, excluded questions,
per-question averages, individual generations and source records. Searching and
filtering do not change the statistical estimate. Cluster deletion sensitivity
links back to the original questions and remains explicitly descriptive.

The [ready-to-open artifact](../examples/reports/copa-comparison.html) was generated
by an installed wheel in a separate Python 3.10 environment containing only
Errorbars and NumPy. It uses the existing **real retained COPA captures** from two
tiny models; it is not a new model run or a synthetic reconstruction of those
logs. All 20 shared IDs have matching document/target signatures. The apparent
+0.2000 difference contains six higher scores, two lower scores and twelve ties.
The paired interval still includes zero. The [walkthrough](comparison-reports.md)
shows how to inspect `copa-15` and find both original line-16 score records.

| Reproduced situation | Earlier behavior | Verified behavior |
| --- | --- | --- |
| Change a COPA document while keeping its ID, scores and vendor doc_hash | All 20 IDs paired; zero difference reported | One content conflict; paired inference withheld; both records inspectable |
| Change a target while retaining the ID | Same ID accepted without a content check | Different versioned content signatures block comparison and leaderboard inference |
| Change only prompt arguments, response or JSON object-key order | Content not checked | Document/target identity still matches; valid prompt comparisons remain possible |
| Omit content evidence | No distinction from a checked match | Unavailable/partial identity is counted separately; signatures are never inherited across models |
| Export native scores and reload the canonical CSV | Content identity discarded | Signatures survive; the installed CLI's native and CSV comparison JSON agree exactly |
| Unequal question sets and repeated generations | Aggregate counts, no case inspection | Complete union retained; missing values stay missing; every observed generation is inspectable |
| 12,000-question report | No report workflow | 40 ledger rows rendered; full JSON retained and downloaded after a one-question filter |
| Dark system preference followed by printing | Initial report styling could retain the dark palette | White print palette with explicit current-page evidence limits |

## Independent checks

The repeated-generation/cohort counterexample has hand-derived means: A = 5/9,
B = 2/3 and A - B = -1/9 over the three shared questions, even though one of them
has three A generations and each model has a separate unmatched question.

Clustered intervals, p-values and standard errors agree with an independent
statsmodels intercept-only OLS fit on the difference vector, using clustered
covariance and Student-t inference. Each deleted-cluster mean is checked by
independently filtering the source questions and averaging the remaining
differences. A dominant-cluster counterexample also verifies that subtraction
from a rounded total does not erase the small remaining groups.

Exact McNemar results are independently checked with SciPy's two-sided binomial
test, including even/odd totals, equal discordances, tiny tails and 100,000
discordant pairs. The production calculation keeps the binomial numerator in
integer arithmetic and reuses adjacent coefficients.

## Local McNemar timing observation

Inputs contain n discordant pairs, with n/2 - 10 A-only successes and n/2 + 10
B-only successes. These are generated benchmark arrays, not evaluation captures.
Each entry below is one wall-clock observation using `time.perf_counter()` on
WSL2 Linux 6.18.40.1, 14 logical CPUs, Python 3.12 and NumPy 2.5.3. Concurrent
machine activity was not controlled; these are not general speedup guarantees.

| Discordant pairs | Earlier implementation | Reusing exact coefficients | p-value (both where measured) |
| ---: | ---: | ---: | ---: |
| 2,000 | 0.03915 s | 0.000699 s | 0.6709544855556545 |
| 12,000 | 4.85383 s | 0.013307 s | 0.8623021999593428 |
| 100,000 | Not measured | 0.654038 s | 0.9520893498136247 |

The timing excludes file parsing and HTML serialization. The previous loop
recomputed `math.comb(n, i)` for every tail term; the new loop uses
`C(n, i) = C(n, i-1) * (n-i+1) // i`. This preserves the exact numerator and
the same final floating-point p-value.

## Fresh installs and actual browser workflows

Source checks ran in a detached clean checkout. Python 3.14 used the committed
lock; Python 3.10 resolved the oldest allowed direct dependencies. A separate
Python 3.10 wheel consumer had only `errorbars 0.2.4` and `numpy 2.2.6` installed,
and imported Errorbars from its own `site-packages`, not the source tree.

| Check | Observed result |
| --- | --- |
| Python 3.14.7, locked dev/all environment | 423 tests passed; Ruff and strict mypy passed |
| Python 3.10.21, minimum direct dependencies | 423 tests passed; one existing Matplotlib/Pyparsing deprecation warning |
| Minimum statistical dependencies | NumPy 1.24.0, SciPy 1.11.1, statsmodels 0.14.0 |
| Source distribution and wheel | Built; HTML/CSS/script/font/license resources included |
| Bare wheel CLI | Native comparison, canonical import/recompare, HTML generation and 4,361-question power example passed |
| New documented source quickstart | `uv sync --locked --no-dev` and both documented report commands succeeded |
| Clean Node 24.21.0 / npm install | Lint, typecheck, 650 planner/vector tests and production build passed |
| Existing planner workflows | 26 passed in Chromium and Firefox |
| Standalone reports generated by installed wheel | 22 passed in Chromium and Firefox, from file URLs with the browser offline |
| Report accessibility | 12 Axe scans across both engines, light/dark, 1440/375/320 px; no violations |
| Browser page errors, CSP violations, HTTP requests | None in the checked report workflows |
| Report evidence boundaries | Full JSON after filtering/paging; CSV across all matched pages; 151-draw sample paging; missing/conflicting cohorts |
| Adversarial labels | Script closing tags, markup, bidi controls and spreadsheet formulas remain inert; JSON retains original identifiers |
| Print path | Explicit and system dark modes use white paper; A4 PDF generated and inspected; current-page limitation retained |

The report tests use actual generated files, real downloads and keyboard focus
transitions. The large fixture is a synthetic 12,000-question **binary** evaluation;
it exercises both the exact McNemar path and browser evidence retention. The
partial-cohort fixture is synthetic and has 120 shared, five A-only and ten B-only
questions, including 151 A observations for one shared question.

Representative commands, run from the clean checkout:

```sh
uv sync --locked --python 3.14 --group dev --extra all
uv run --no-sync ruff check .
uv run --no-sync mypy src/errorbars
uv run --no-sync pytest -q
uv build

uv venv --python 3.10 .venv-minimums
uv pip install --python .venv-minimums --resolution lowest-direct -e '.[all,inspect]' --group dev
.venv-minimums/bin/pytest -q

uv venv --python 3.10 .report-venv
uv pip install --python .report-venv dist/errorbars-0.2.4-py3-none-any.whl

npm ci --prefix web
npm run lint --prefix web
npm run typecheck --prefix web
npm test --prefix web
npm run build --prefix web
npm run test:browser --prefix web
ERRORBARS_REPORT_PYTHON="$(pwd)/.report-venv/bin/python" npm run test:reports --prefix web
```

The static calculator still builds to `web/dist/` with `npm run build --prefix web`.
Comparison reports are generated by the Python command into the requested HTML
path; they need no frontend build or hosting deployment.

## Visual evidence and scope

Screenshots were opened and visually inspected:

- [Overview](assets/comparison-overview.png)
- [Chromium evidence view](assets/comparison-evidence.png)
- [Firefox evidence view](assets/comparison-firefox-evidence.png)
- [Phone evidence in dark mode](assets/comparison-mobile-dark.png)

The layout preserves the existing Spectral / IBM Plex visual style. Phone rows
prioritize the question, difference and coverage; individual A/B scores remain
in the selected-question inspector. Charts keep readable axis text as the viewport
changes. The browser capture manifest records the actual Chromium 153.0.8010.12
and Firefox 155.0 engines; [artifact hashes](verification-comparison-assets-2026-10-07.json)
identify the committed report and images. No Safari or physical-device claim is made.

Fingerprint equality is an exact check under the supplied scheme, not proof of
metric equivalence or representative sampling. Inspect and legacy inputs may
have no content signatures. Source locations identify imported records, not a
cryptographically verified copy of the whole file. Full input parsing and browser
JSON loading remain proportional to total evidence size. Printed output retains
only current pages; the HTML/JSON carries the complete ledger.

Local Beads tracking in Officina: `officina-lg3` (comparison workflow),
`officina-am1` (question-content integrity), `officina-5yp` (McNemar scale).
These are local records, not published issues. Implementation commits:
`ab34a98`, `82028f7`, `58ff8ed`, `ff71d8a`.
