# Metric contract verification, 2026-10-15

The [study](../studies/metric-contract/README.md) retains newly generated,
unedited lm-eval 0.4.13 logs, the [baseline failure](../studies/metric-contract/results/before.json),
the [corrected replay](../studies/metric-contract/results/after.json), and the
[verification receipt](../studies/metric-contract/results/verification.json).
These are constructed log likelihoods passed through the real harness, not
measurements of trained models or evidence of model quality.

## Result

Mean negative log likelihood now ranks the lower loss first: `precise`, 0.25,
ahead of `noisy`, 0.790625. The previous order was reversed. The higher-is-better
likelihood control keeps its order and values. Original scores, mean units,
confidence intervals and two-sided significance calculations are preserved.
Tests compare the native runs' paired p-values to independent SciPy results.

Native perplexity is refused before inference or exports: the recorded
aggregation is exponential, while the scalar sample inputs are log likelihoods.
The old means of -0.25 and -0.790625 do not estimate the harness's perplexities
of 1.2840254166877414 and 2.204773979462882. This change does not implement
perplexity-specific inference.

Recorded directions survive CSV/JSONL/DataFrame loading, model selection,
concatenation and standalone comparison downloads. Explicit direction cannot
contradict recognized input evidence. Rejected operations preserve existing
CSV, SVG and HTML files. The ordinary `mean` aggregation remains supported,
as does `nanmean` on the finite inputs accepted by errorbars.

## Clean source and packages

Implementation commits:

```text
d949050 fix: honor recorded metric direction and aggregation
86497b1 fix: retain finite nanmean metric imports
```

The final Python verification uses a fresh `git archive` of `86497b1` and a
fresh environment. The receipt records the complete commit ID, archive hash,
wheel and source-distribution hashes. Later documentation commits retain
evidence; their runtime source files are byte-checked against this archive.

| Environment | Checks |
| --- | --- |
| Clean Python 3.14.7, locked NumPy 2.5.3 | Ruff, mypy on 20 source files, all 763 tests, wheel and sdist build |
| Installed wheel: Python 3.10.21, NumPy 1.24.0 | Only errorbars and NumPy installed; 17 actual CLI workflows; all 28 runtime files match source |
| Installed wheel: Python 3.14.7, NumPy 2.5.4 | Same 17 workflows and 28 source-byte comparisons; independent of the source checkout |
| Node 24.21.0 and 26.7.0 | Web lint, typecheck, all 691 tests and production builds; all 65 built files byte-identical |
| Chromium and Firefox | 32 standalone-report checks and 52 production-page checks |

The web and browser suites used the first implementation archive. Their
web source, packaged report JavaScript/CSS/fonts and report-fixture generator
are unchanged in `86497b1`. Final wheel-generated browser artifacts are
hash-compared to the actual inspected artifacts; those bytes are identical.
The final guard refinement is exercised by the full Python suite and the
installed CLI's additional finite-`nanmean` workflow.

The isolated wheel environments run outside a checkout and contain no Rich,
Inspect, pandas, SciPy, pytest or editable errorbars installation. The CLI
therefore also verifies the dependency-free text-table path. Both run the
documented power quickstart and return `Questions needed: 4361`.

Commands used inside the fresh source archive:

```bash
uv sync --locked --python 3.14 --group dev --extra all
.venv/bin/ruff check .
.venv/bin/mypy src/errorbars
.venv/bin/pytest -q
uv build
```

Then, starting in the checkout, install and run the wheel outside it:

```bash
metric_source=$PWD
metric_run=$(mktemp -d)
uv venv --python 3.10 "$metric_run/wheel310"
uv venv --python 3.14 "$metric_run/wheel314"
uv pip install --python "$metric_run/wheel310/bin/python" "$metric_source/dist/errorbars-0.2.4-py3-none-any.whl" numpy==1.24.0
uv pip install --python "$metric_run/wheel314/bin/python" "$metric_source/dist/errorbars-0.2.4-py3-none-any.whl"
cd "$metric_run"
for metric_tag in 310 314; do
  "$metric_run/wheel$metric_tag/bin/python" "$metric_source/studies/metric-contract/replay.py" --out "replay$metric_tag.json"
  "$metric_run/wheel$metric_tag/bin/python" "$metric_source/studies/metric-contract/verify.py" --out "workflows$metric_tag.json" --artifacts "artifacts$metric_tag"
done
```

The scripts need only errorbars and NumPy. The receipt records the installed
package versions. The report JavaScript and bundled fonts are checked as
installed files, rather than read from a developer checkout.

Web commands, in `web/` after a clean `npm ci`:

```bash
npm run lint
npm run typecheck
npm test
npm run build
npm run test:reports
npm run test:browser
```

`ERRORBARS_REPORT_PYTHON` points the report suite to the separately installed
wheel. Cached Chromium and Firefox are used; no browser install was run.
The static build output is **`web/dist/`**. No deployment followed.
Text logs replace only the temporary absolute checkout prefix with
`<checkout>`; results and measurements are unchanged.

## Offline artifacts and visual inspection

The [browser receipt](../studies/metric-contract/results/browser.json) records
four fresh contexts: Chromium and Firefox, each at 1440 and 375 pixels.
Networking is disabled before the first file load. Each context opens the
actual wheel-generated HTML and SVG, filters to one question, inspects its
original records, downloads full JSON and filtered CSV, and checks rank order.
There are no page errors or HTTP requests.

Downloaded JSON exactly matches all 32 questions in the embedded evidence;
filtering does not discard the other 31. The one-row CSV keeps `[false]` for
both models and the original scores 0.1 and 0.6. All four downloaded CSVs were
also parsed with Python's independent CSV reader; the
[receipt](../studies/metric-contract/results/csv-download-checks.json) records
those checks.

All six screenshots were opened and inspected. The existing report layout
stays readable at phone width, wraps the long native source names, and has no
horizontal overflow. Both plot renderers identify the original-unit,
lower-first ordering; the SVG was inspected in both browser engines.

- Report: [Chromium desktop](assets/metric-contract/chromium-1440-report.png),
  [Chromium phone](assets/metric-contract/chromium-375-report.png),
  [Firefox desktop](assets/metric-contract/firefox-1440-report.png),
  [Firefox phone](assets/metric-contract/firefox-375-report.png).
- SVG: [Chromium](assets/metric-contract/chromium-forest.png),
  [Firefox](assets/metric-contract/firefox-forest.png).

## Limits and status

Missing metric declarations remain unknown. Without any direction declaration,
the historical higher-first ranking remains available and is explicitly labelled
`default`; callers can supply `--score-direction lower`. A partial declaration
produces a warning about the assumed common direction. Known conflicting
directions cannot be overridden by that flag. Matching declarations establish
neither source authenticity nor equivalent custom scorer code.

This is local source work, with locally built and tested artifacts. No source
push, hosted update, version tag or package publication was performed.
The existing project description remains appropriate: "Error bars for LLM
evals: standard errors, clustering, paired comparisons, leaderboards, and power analysis."
Relevant topics: `llm-evaluation`, `statistics`, `confidence-intervals`,
`benchmarking`, `paired-tests`, `python`.
