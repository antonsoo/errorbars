# Walkthrough: a leaderboard win that evaporates

This walkthrough uses `examples/data/reading_comprehension.csv`, a
**synthetic** (simulated, not real) reading-comprehension benchmark:
40 passages, 5 questions per passage (200 questions total), 4 synthetic
models. Regenerate it any time with:

```bash
python examples/generate_synthetic.py
```

The generator (`examples/generate_synthetic.py`) gives every question a
shared passage-difficulty effect and question-difficulty effect — the
reason questions in the same passage are correlated, and the reason
clustered standard errors matter here. `tuned-70b` has a small *true*
ability edge over `baseline-70b` (ability logits 0.68 vs 0.55) baked into
the simulation, deliberately small enough to be hard to detect at this n.

All numbers below are copied verbatim from running the commands shown.

## Step 1: the naive leaderboard

```console
$ errorbars leaderboard examples/data/reading_comprehension.csv
```

| rank | model | mean | 95% CI |
|---|---|---|---|
| 1 | tuned-70b | 0.690 | [0.626, 0.754] |
| 2 | baseline-70b | 0.620 | [0.553, 0.687] |
| 3 | tuned-7b | 0.535 | [0.466, 0.604] |
| 4 | baseline-7b | 0.470 | [0.401, 0.539] |

Read as a bare leaderboard, `tuned-70b` beats `baseline-70b` by 7 points —
looks like a real win, and their independently-computed CIs barely
overlap.

## Step 2: pair on the shared questions

`tuned-70b` and `baseline-70b` saw identical questions, so the right
comparison is paired, not two independent means:

```console
$ errorbars compare examples/data/reading_comprehension.csv \
    --model-a tuned-70b --model-b baseline-70b
```

| metric | value |
|---|---|
| mean diff (A - B) | 0.0700 |
| paired SE | 0.0440 |
| 95% CI | [-0.0162, 0.1562] |
| p-value | 0.1116 |
| correlation(A, B) | 0.1434 |
| unpaired SE (for reference) | 0.0475 |
| variance reduction from pairing | 14.3% |
| McNemar discordant (A wrong/B right, A right/B wrong) | 32 / 46 |
| McNemar exact p-value | 0.1405 |

Pairing already shrinks the SE by 14% and the 95% CI now crosses zero.
McNemar's exact test on the same discordant pairs agrees: p = 0.14.

## Step 3: account for clustering

The 200 questions are not 200 independent trials — they're 40 passages of
5 questions each, and passage difficulty affects every question in it.
`compare` and `leaderboard` pick up the `cluster_id` column automatically
and report a cluster-robust paired SE/CI/p-value alongside the naive one
(`errorbars compare ... ` shows `clustered paired SE` and `clustered CI`
rows when a `cluster_id` column is present):

```console
$ errorbars leaderboard examples/data/reading_comprehension.csv --json
```

The pairwise entry for this pair:

```json
{"model_a": "tuned-70b", "model_b": "baseline-70b", "mean_diff": 0.07,
 "p_value": 0.1116, "p_holm": 0.2982}
```

`p_holm` (0.298 — the cluster-robust p-value, Holm-corrected across all 6
pairwise comparisons on the leaderboard) is *larger* than the naive 0.112:
clustering and the multiple-comparison correction both push against
significance here. The leaderboard's own grouping output says the same
thing directly — `tuned-70b` and `baseline-70b` share a group letter:

```
rank  model         mean    95% CI              group
1     tuned-70b     0.6900  [0.6257, 0.7543]    a
2     baseline-70b  0.6200  [0.5526, 0.6874]    ab
3     tuned-7b      0.5350  [0.4657, 0.6043]    bc
4     baseline-7b   0.4700  [0.4007, 0.5393]    c
```

**The apparent win is not statistically significant.** It already wasn't
once it had a proper error bar: the unclustered paired test in Step 2 gave
p = 0.11. Accounting for the fact that these are 40 passages of 5
questions each, and Holm-correcting across all 6 pairwise comparisons on
the board, pushes that further to p = 0.30. `tuned-70b` and `baseline-70b`
are not distinguishable at α=0.05 either way — a naive leaderboard that
just ranks by bare accuracy would still have shipped the 7-point gap as a
win.

## Step 4: how many questions *would* settle it?

`errorbars summarize --model tuned-70b` reports this dataset's measured
ICC (0.071) and design effect (1.284, for average cluster size 5) for that
model. Feed the observed correlation (0.1434) and design effect into
`power` to ask how many questions would be needed to reliably detect gaps
of this size:

```console
$ errorbars power --delta 0.07 --baseline 0.655 --rho 0.1434 --cluster-deff 1.284
Questions needed: 797

$ errorbars power --delta 0.05 --baseline 0.655 --rho 0.1434 --cluster-deff 1.284
Questions needed: 1561
```

200 questions across 40 passages is nowhere near enough to reliably detect
a gap this size (797-1561 needed, depending on the true effect) — which is
exactly why the leaderboard couldn't distinguish these two models.

## Bonus: repeated sampling and decoding noise

`examples/data/repeated_sampling.csv` has one model answering 60 questions
with 4 sampled generations each — synthetic data for the within/between
variance decomposition:

```console
$ errorbars summarize examples/data/repeated_sampling.csv --model tuned-7b
```

| component | variance |
|---|---|
| within-question (sampling noise) | 0.2181 |
| between-question (item difficulty) | 0.0304 |

Most of the variance here (88%) is decoding noise, not item difficulty —
in this synthetic setup, sampling more generations per question would
tighten the estimate faster than adding more questions (see
`docs/formulas.md` §6 for the formula and why).
