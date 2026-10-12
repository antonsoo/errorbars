# Binary plans must describe possible paired outcomes

The baseline source `6adea05815b239b5dd945b104e92f3033a3167e7`
returned precise budgets for some impossible single-answer binary comparisons.
The existing caveat disclosed that joint Bernoulli constraints were not checked,
but the UI still displayed and exported the numbers as usable plans.

| Assumptions (default alpha .05, power .8) | Before | Repaired source |
| --- | --- | --- |
| Baseline .8, improvement .05, correlation 1 | 2 questions | Unavailable: no positive improvement can have perfect positive correlation |
| Baseline .9, improvement .05, correlation .9 | 57 questions | Unavailable: the joint table would have a negative cell |
| Baseline .8, 100 questions, correlation 1 | MDE 0 | Unavailable |
| Baseline .2, 1,000 questions, correlation -.5 | MDE .0613796568 | MDE .3, limited by the smallest possible gap at that correlation |
| Baseline .9, 135 questions, correlation .5 | MDE .0723366193 | Same valid primary result; correlation-zero sensitivity is unavailable |
| Baseline .5, improvement .03, correlation .3 | 3,053 questions | 3,053 questions |

Full CLI output is retained in [before.json](results/before.json) and
[source.json](results/source.json). The four-cell derivation and numerical
boundary policy are in [formulas.md](../../docs/formulas.md#binary-feasibility).
The [planning guide](../../docs/planning.md) describes version 2 browser exports
and the distinct scope of continuous and repeated-answer variance models.

## Independent checks

`check.py` evaluates joint probabilities using 70-digit Decimal arithmetic on
the exact floating-point input values; it does not call the production interval
formula to decide the expected sign. It also enumerates every 2x2 integer table
with totals 5, 10, 20 and 40, interior marginals and a strictly better second
model. Correlations derived from those counts are rounded toward zero when
converted to floats, preserving the boundary to numerical precision.

- All **6,776** tables produce accepted forward plans and feasible inverse gaps.
- A separate **1,781-case** grid has **673** feasible inputs under exact Decimal
  evaluation. There are no material classification disagreements. Five
  floating-point boundary differences are retained explicitly: three accepted
  perfect-negative cases with negative cells of magnitude at most `2.78e-17`,
  and two rejected targets whose floating-point accuracy sum rounds to 1.
- **15,238** production Python/TypeScript calls agree, including exact integer
  counts and MDE floats on this run. Ninety-five tiny-effect grid inputs need
  question counts beyond the existing representable range; their feasibility
  is checked with the public range API, and they are excluded from numeric
  cross-language budget comparison.
- The smallest inverse joint cell among the integer-table checks was about
  `-6.92e-17`, within floating-point boundary tolerance. This is not exact real
  arithmetic and does not establish the calibration of the power approximation.

See the complete [oracle receipt](results/oracle.json). Existing 400 forward
and 200 inverse cross-language fixtures retain all their input combinations;
51 forward and 46 inverse entries now expect an explicit feasibility error.

## Reproduce

From the repository root, after the development dependencies are installed:

```bash
uv run python studies/binary-feasibility/check.py --output /tmp/binary-oracle.json
uv run python studies/binary-feasibility/workflows.py --expect after --output /tmp/binary-cli.json
npm --prefix web ci && npm --prefix web run build
node studies/binary-feasibility/browser.mjs web/dist /tmp/binary-browser after
```

The native TypeScript runner needs Node 24 or newer (`--node` selects an
executable). The browser runner uses the installed Playwright Chromium and
Firefox engines. It tests 1440px and 375px viewports, physically stops its local
server after initial loading, then edits impossible/feasible plans and saves
actual JSON downloads. It checks accessibility, overflow, browser errors,
external requests and CSP violations, and records hashes of served assets.
It saves one desktop rejection and one mobile correlation-minimum screenshot
per engine. Run it against the preserved baseline build with `before` to
reproduce the earlier UI and exports.

The CLI runner uses the Python interpreter executing the script, so the same
13-case workflow can be run from an isolated wheel installation. To inspect the
baseline, use an isolated checkout of the pinned commit and its installed CLI
or set `PYTHONPATH` to that checkout's `src` with `--expect before`.

## Scope

The common-baseline-variance normal approximation is unchanged. Feasibility
does not establish target power, and large gaps or small samples still require
a different calculation or simulation. This check applies to one binary answer
per model per question. It does not check the joint feasibility of continuous
scores or averages of repeated answers, and does not estimate correlation or
cluster assumptions from data. Package and hosted-site publication are separate
from source changes.
