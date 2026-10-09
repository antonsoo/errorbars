# A binary leaderboard must use its binary test

With two shared binary questions, candidate=[1,1] and baseline=[0,0], the
leaderboard used to print p=0 and separate the models into different groups.
`paired_compare` already computed the exact McNemar p=0.5, but the leaderboard
ignored it and used its degenerate paired-t diagnostic.

The repaired leaderboard selects a test from the structure of each pair's
**shared observations**, before applying Holm across the whole board:

| Shared data | Selected test | JSON `test` |
|---|---|---|
| Multiple questions grouped in clusters | Existing CR2 clustered t test | `clustered_t` |
| One binary score per question, no grouped questions | Exact McNemar | `mcnemar_exact` |
| Continuous scores or repeated-generation question means | Paired t | `paired_t` |

Singleton cluster labels do not create dependence. Repeated generations on
unmatched questions do not change a binary shared comparison. Repeated means
that happen to equal 0 or 1 remain on the paired-t path. The method is never
chosen by the smaller of two p-values. Boards with mixed methods still have
one Holm family.

![Actual CLI output: two questions produce p=0.5 and a shared group](assets/leaderboard-exact.png)

The terminal table names the selected test and prints both its raw and
adjusted p-value. JSON adds `test`, `p_value_used`, and `mcnemar`; the existing
`p_value` continues to mean the unclustered paired-t diagnostic for compatibility.
Consumers should use `p_value_used` for the selected raw test and `p_holm` for
grouping. `compare` still exposes its existing diagnostics. No estimator or
question weighting changed in this repair.

## Independent checks

For discordant binary pairs, the exact test uses the binomial distribution;
see the [statsmodels McNemar documentation](https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html).
The small-table checks compare the selected leaderboard result against that
implementation. Holm results are also compared against
[statsmodels multipletests](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html).

The retained audit also enumerates a conditional null exactly: all questions
are discordant, with either model equally likely to win each independent
question. These are exact probabilities, not Monte Carlo estimates and not
an empirical benchmark of model quality:

| Discordant questions | Prior paired-t rejection probability | Exact rejection probability |
|---|---:|---:|
| 2 | 0.500000 | 0.000000 |
| 3 | 0.250000 | 0.000000 |
| 4 | 0.125000 | 0.000000 |
| 5 | 0.062500 | 0.000000 |
| 6 | 0.031250 | 0.031250 |
| 8 | 0.070313 | 0.007813 |
| 10 | 0.021484 | 0.021484 |
| 20 | 0.041389 | 0.041389 |
| 40 | 0.038477 | 0.038477 |

The nominal level is 0.05, with rejection at p<0.05. At two questions, both
outcomes matching has probability one half; the prior t convention reports
zero variance and p=0 for those outcomes. The exact test cannot reject at
that sample size. Discreteness can make it conservative.

## Retained real inputs

The [audit script](../studies/leaderboard-tests/audit.py) reuses the existing
[pinned SWE-bench outcomes](../studies/swe-bench-verified/README.md) and native
lm-eval logs. It downloads nothing. The same two submissions excluded by the
original SWE-bench study for contradictory reported scores stay excluded.
Both old and new leaderboard policies use the same current readers and
comparison functions.

| Analysis | Models | Questions | Pair tests | Previously significant | Now significant |
|---|---:|---:|---:|---:|---:|
| SWE-bench, treating tasks as independent | 173 | 500 | 14,878 | 10,720 | 10,657 |
| SWE-bench, clustered by repository | 173 | 500 | 14,878 | 1 | 1 |
| Native lm-eval COPA captures | 2 | 20 | 1 | 0 | 0 |

In the task-independent analysis, 64 pairs cease to be significant and one
becomes significant after the changed raw values pass through Holm. The
exact result is not uniformly larger than the t approximation. The number
of maximal groups remains 117, though pair edges change. Repository-clustered
p-values and groups are **exactly unchanged**. This is a regression check of
the selection policy, not evidence that SWE-bench tasks are independent.
The repository grouping is preserved by the study's default CSV exporter.

For the two real COPA captures, the selected p-value changes from 0.162550 to
0.2890625, based on 6 versus 2 discordant wins. The two models remain in one
group. The standard-library CLI replay reconstructs these counts directly
from native sample records, checks their 20 shared document IDs, and checks
the exact tail independently of Errorbars' adapter.

The [retained audit](../studies/leaderboard-tests/results.json) contains input
and code hashes, exclusions, exact null probabilities, every changed pair,
and the native COPA before/after report. Reproduce from a development install:

```bash
uv run python scripts/verify_leaderboard_tests.py --out /tmp/leaderboard-workflows.json
uv run python studies/leaderboard-tests/audit.py --out /tmp/leaderboard-audit.json
```

The audit needs statsmodels from the development dependencies. The installed
CLI replay uses only the standard library in its driver and NumPy in the
package. [The tiny counterexample](../examples/leaderboard-tests/README.md)
also retains complete CLI before/after JSON.

## Limits

Failing to separate two models is not evidence of equivalence. Exact McNemar
requires independent paired binary observations; it does not correct hidden
question dependence, unmatched populations, leaked benchmark questions, or
adaptive selection of evaluations. Explicit clusters take precedence.
Continuous and repeated-generation t inference retains its assumptions and
zero-variance warnings. The change does not turn marginal intervals into
simultaneous intervals, and different model means can still cover different
question sets. All changes here are local and unreleased.
