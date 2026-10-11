# Partial-cohort leaderboards and identity-check cost

The source checkout retains a leaderboard when two models share many questions
but only one independent cluster. Their comparison is untested; the other
comparisons and model estimates remain available. The same change indexes
question signatures per model instead of scanning every observation for each
pair. Neither change alters the statistical formulas.

These repairs are source changes. No PyPI release or manual hosted update was made.

## A board that previously aborted

[`partial-cohorts.csv`](partial-cohorts.csv) is a **synthetic** reading-comprehension
example with four models and three passages, ten questions per passage. Its
identity declarations are synthetic too. It is not a model-quality study.

| Model | Passages evaluated | Questions |
|---|---|---:|
| model-a | 1, 2 | 20 |
| model-b | 1, 3 | 20 |
| model-c | 2, 3 | 20 |
| model-d | 1, 2, 3 | 30 |

Every model has enough groups to compute its own cluster interval. But a/b,
a/c and b/c each share only one passage. Ten questions from one passage do
not supply two independent clusters for a clustered paired test.

At revision `c6826fe55edf60916bb3954ef6f6756280589ccb`, the real CLI exited 1
and produced no leaderboard:

```text
error: need at least 2 independent clusters; one cluster cannot estimate a clustered SE
```

The corrected command exits 0, keeps four model estimates, performs the three
comparisons involving model-d, and records the other three in `untested_pairs`
with `reason: "fewer_than_two_shared_clusters"` and `n_shared: 10`. The table and
SVG identify the exact untested ranks. The board-wide warning explains the
cluster limitation. No p-value, significance decision, or non-significant group
membership is invented for an untested pair.

The three eligible p-values agree with the existing dense-matrix CR2 reference
and SciPy's Student t distribution. Their adjusted p-values agree with
statsmodels Holm correction applied to those three tests. The regression also
checks an entirely untestable board, mixed unavailable reasons, and a content
conflict that must still be rejected before testing eligibility.

- [Captured failure](results/before.json) and [corrected JSON](results/after.json),
  including input and library-module SHA-256 hashes.
- [Complete terminal output](results/terminal.txt) and [SVG export](results/partial-cohorts.svg).
- [Terminal capture](../../docs/assets/leaderboard-overlap.png),
  [Chromium SVG capture](../../docs/assets/leaderboard-overlap-chromium.png), and
  [Firefox SVG capture](../../docs/assets/leaderboard-overlap-firefox.png).
  Both browsers rendered the SVG offline; all 31 text labels stayed inside its
  bounds and all three untested-rank annotations were present.
  [Rendering receipt](results/rendering.json).

## Cost of retaining question identity

The benchmark uses unchanged per-task scores from the repository's retained
[SWE-bench data](../swe-bench-verified/data/outcomes.json), taking the top 40, 80,
and 120 submissions by recorded resolved count, with ID as the tie-breaker.
It adds synthetic hashes of question IDs to exercise the identity-validation
path. These hashes are **not independently verified content signatures**. The
experiment measures computation, not model accuracy or the completeness of the
source benchmark. It omits cluster labels and uses the binary question-level
test throughout.

Median elapsed seconds of three calls on a shared 14-vCPU WSL2 Linux workstation
with 48 GB RAM, Python 3.12.12:

| Models | Questions per model | Tested pairs | Before, identities present | After, identities present |
|---:|---:|---:|---:|---:|
| 40 | 500 | 780 | 1.258 | 0.614 |
| 80 | 500 | 3,160 | 9.517 | 1.771 |
| 120 | 500 | 7,140 | 31.315 | 5.911 |

All six cases (each board with and without identity declarations) have exactly
the same complete output hashes before and after. The captured runtime includes
all validation, statistical inference and grouping inside `build_leaderboard`;
file loading and JSON serialization are outside the timed region. Other work was
running on the workstation, so these are observed timings, not an isolated
microbenchmark or a latency guarantee.

[Before measurements](results/performance-before.json) and
[after measurements](results/performance-after.json) retain individual timings,
Python/platform information, source-data and implementation hashes, and full
output hashes. Indexing removes the repeated all-model scans from identity
checks; pairwise inference and graph grouping still have their own costs.

## Reproduce with the package being checked

From the repository root, use the Python environment whose installation you
want to check. Neither script changes `sys.path` or installs the source package:

```bash
python studies/leaderboard-overlap/reproduce.py --out /tmp/overlap.json
python studies/leaderboard-overlap/benchmark.py --models 40 80 120 --repeat 3 --out /tmp/overlap-timing.json
errorbars leaderboard studies/leaderboard-overlap/partial-cohorts.csv --plot /tmp/partial-cohorts.svg
```

## Limits

Each displayed model mean still uses that model's own cohort; the warning about
different questions remains. An untested pair establishes neither equality nor
a difference. One-cluster model intervals themselves still raise an error; this
repair concerns pair intersections within otherwise estimable boards. Scoring
and content conflicts still reject the board, including conflicts in an
otherwise untestable pair. Sparse cluster intervals can be very wide and extend
outside the binary score range; the example retains them without clipping.

## Installation check

Source revision `4deac31` passed lint, strict type checking, and 593 tests under
Python 3.12.12. A clean `git archive` then passed `uv sync --locked --group dev
--extra all`, `ruff check .`, `mypy src/errorbars`, all 593 tests under Python
3.14.7, and `uv build` (source distribution and wheel).

The resulting wheel was installed into a fresh Python 3.12 environment with
only its required NumPy dependency. Running outside the checkout, the partial
cohort JSON and SVG matched the source artifacts byte for byte; the plain
terminal table worked without Rich. The README power quickstart returned 4,361
questions and its reading-comprehension leaderboard completed.
[Wheel hash and verification receipt](results/verification.json).
