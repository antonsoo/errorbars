# Data-integrity verification - 2026-10-04

This subsequent audit corrected question weighting, paired inference, input ambiguity and
resampling memory in the Python package. Changes are local and unreleased; no source push,
site deployment or package publication was performed. The earlier planner release remains
documented separately in [its verification report](verification-2026-10-04.md).

Implementation commits: `e60779a` (paired inference and bootstrap), `5db1e52` (input and
adapter integrity), `6f1d688` (question weighting and regression coverage), and `9f5eb86`
(supported browser lint tooling), and `bf3c7e6` (nullable pairing diagnostics).

## Counterexamples and outcomes

The starting checkout passed all 293 Python tests, including the formerly failing narrow
terminal case. The first 45 additional counterexample checks produced 42 failures. Later
adapter checks produced 12 failures out of 20, and all seven bootstrap boundary/allocation
checks failed before their fixes. Four more checks reproduced undefined diagnostics
being exported as zero. The completed suite contains 97 additional cases.

| Input or trigger | Earlier result | Verified result |
| --- | --- | --- |
| Ten successes for q1, one failure for q2 | Mean 10/11, n=11; ranked above a model with question mean 0.7 | Mean 0.5, n=2, observations=11; equal question weighting agrees with paired means |
| Four generations of each of 60 questions | Per-draw primary SE with n=240 | Question mean 0.5542, question SE 0.0376, n=60; all 240 draws retained for variance decomposition |
| Exactly constant positive/negative paired differences | p=1 despite a nonzero difference | p=0 limiting t-test result, plus an explicit degeneracy warning |
| Constant score vectors | Undefined correlation/reduction exported as zero | JSON null, CLI unavailable, and explanatory warnings; defined tests remain available |
| Continuous score units near 1e-200 | Squared residuals underflowed; false zero SE, ICC and component variances | Rescaled SE/correlation/ICC; unrepresentable squared-unit components produce a rescaling error |
| Matrix or nonfinite scores, unequal McNemar vectors, nearly binary grades | Flattened counts, broadcasting or guessed binary outcomes | One-dimensional aligned finite vectors; McNemar requires exact 0/1 |
| One independent cluster | Ordinary independent-observation SE labelled clustered | Explicit error: at least two independent clusters are required |
| Duplicate score columns or JSON keys | Last grade silently overwrote the earlier value | Duplicate normalized CSV names and JSON fields are rejected |
| Null/structured IDs or conflicting cluster assignments | Fake identifiers or first-assignment-wins grouping | Row/source errors; a question has one cluster across models and samples |
| Unlabelled source combined with clustered data | Invented singleton groups could override known metadata | Only assignments for the same question propagate; unknown questions require metadata |
| Inspect grade None/pending, or an unscored sample | Zero score, or silently omitted observation | Sample-specific error; valid vendor codes/numbers retain their conversion |
| lm-eval record without a valid doc_id | Invented identity based on row order | Missing/invalid identity is rejected; duplicate grade fields remain visible errors |
| 4,000 questions, default 10,000 bootstrap draws | Full 40-million-element index matrix plus indexed scores | Batched indices; every resample mean and seeded percentile retained |

The runnable [synthetic unequal-repetition fixture](../examples/data/unequal_repetitions.csv)
and its [walkthrough](../examples/README.md#unequal-repeated-generations) make the weighting
change inspectable. Both text and JSON distinguish questions from observations. The real
[terminal capture](assets/repeated-generations-terminal.png) was opened and visually reviewed.

## Independent oracles and evidence boundaries

Ordinary paired results still match SciPy. The nonzero constant-difference case agrees
with SciPy's p=0 limit. Identical scores retain p=1 **by explicit convention**: SciPy returns
NaN for 0/0, so this is not claimed as agreement. Both cases include warnings and retain
the separate exact McNemar result for binary pairs. A zero-width interval does not establish
population certainty. See [SciPy's paired-test definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_rel.html).

Tiny-unit comparisons are checked against SciPy on rescaled values, rather than against
its raw tiny-unit result, which itself underflows. Independent statsmodels OLS on question
averages checks unequal repeats and unequal passage sizes; Student-t critical values use
the independent cluster count minus one. Refusing a single cluster follows the singular
CR1 correction G/(G-1) in the [statsmodels implementation](https://www.statsmodels.org/stable/_modules/statsmodels/stats/sandwich_covariance.html#cov_cluster).

Bootstrap batches match a separately constructed one-shot seeded resampling oracle for
both percentile endpoints and SE. Instrumentation delegates to the real random generator
and counts its allocation requests: no batch exceeds 250,000 indices when a single
resample fits that budget, and the full requested resample count is preserved. Existing
Monte Carlo coverage tests continue to pass. Resample counts must be integers of at least two.

Inspect checks modify in-memory copies of the real retained fixture; one CLI test serializes
a modified copy to a temporary JSON log and lets Inspect parse it. The original fixtures
are unchanged and no models are called. The recognized conversion follows Inspect's
[own scorer implementation](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/scorer/_metric.py);
unsupported values are refused before its zero fallback. The adapter remains tested against
Inspect 0.3.268. Missing planned questions outside the captured log cannot be reconstructed.

## Fresh-install checks

The implementation was tested in a detached clean checkout. Python installations used
the committed stable-preferred lock or an explicit lowest-direct resolution. Node used
24.21.0 and npm 11.19.0. Cached Chromium and Firefox were reused; no browser install was run.

| Check | Result |
| --- | --- |
| Source Python 3.12.12 / NumPy 2.5.3 | 390 tests passed |
| Clean Python 3.14.7, locked dev/all dependencies | 390 tests passed; Ruff and strict mypy passed |
| Clean Python 3.10.21, lowest compatible direct dependencies | 390 tests passed; one Matplotlib/Pyparsing deprecation warning |
| Source distribution and wheel | Built successfully |
| Bare Python 3.10 wheel consumer | Installed with NumPy only; planning, repeated summaries, plain tables and paired API passed |
| Missing Inspect extra in bare consumer | Clear recovery command, no traceback |
| Clean Node 24 lint/types | Passed |
| TypeScript unit/vector suite | 650 tests passed |
| Production browser suite | 26 workflows passed in Chromium and Firefox |
| Accessibility in those workflows | 16 Axe scans; zero violations under the default rules |
| Browser page errors, CSP violations, off-origin requests | None observed in the checked workflows |
| ESLint 10 migration | Valid peer tree; production files match the browser-tested build |

Minimum direct versions included NumPy 1.24.0, SciPy 1.11.1, statsmodels 0.14.0,
pandas 1.5.0 and Matplotlib 3.7.0. The bare consumer used NumPy 2.2.6 with no Rich,
Inspect, scipy or statsmodels installed. It imported the built wheel from its own site-packages.

```sh
uv sync --locked --python 3.14 --group dev --extra all
uv run --no-sync ruff check .
uv run --no-sync mypy src/errorbars
uv run --no-sync pytest -q
uv build

uv venv --python 3.10 .venv-minimums
uv pip install --python .venv-minimums --resolution lowest-direct -e '.[all,inspect]' --group dev
.venv-minimums/bin/pytest -q

npm ci --prefix web
npm run lint --prefix web
npm run typecheck --prefix web
npm test --prefix web
npm run build --prefix web
npm run test:browser --prefix web
```

CLI quickstart and documented synthetic/harness examples were also exercised locally.
The 3-point gap command still returns 4,361 questions; the documented clustered power
example returns 1,573. The real two-model COPA fixture still gives a -0.2 paired difference
over 20 shared questions and p=0.16255. The normal-approximation power model is unchanged;
its shared Python/TypeScript vectors remain current.

## One bootstrap memory observation

The same command, in separate processes on Python 3.12.12 / NumPy 2.5.3, used
`np.linspace(0, 1, 4000)` and `bootstrap_ci` with default seed and 10,000 resamples.
Machine: WSL2 Linux 6.18.40.1, AMD Ryzen 7 7800X3D, 14 logical CPUs.

| Measurement | Full allocation | Batched allocation |
| --- | --- | --- |
| Process peak RSS | 644.9 MiB | 40.1 MiB |
| Observed elapsed time | 44.568 s | 0.149 s |
| Mean | 0.5000000000000001 | 0.5000000000000001 |
| Lower percentile | 0.491111457551888 | 0.491111457551888 |
| Upper percentile | 0.5087933233308327 | 0.5087933233308327 |

These are single local observations under uncontrolled concurrent machine load, not a
general speedup guarantee. RSS includes the Python process and NumPy. Working storage is
O(n+B), but a large input still requires at least one full resample and runtime remains
O(nB); batching is not a work or cancellation limit.

## Production artifacts and local tracking

All 56 production files match the build exercised by both browsers. Representative hashes:

| File | SHA-256 |
| --- | --- |
| index.html | 4a185ef34094a5d6258f640062453857e4292af4cdd163546dd83dde07975126 |
| assets/index-ChRUxLQK.css | 489f7e15c43bde01af12a2e4a6991885b8b4e45c5dcbde51b5026176fa63b1ea |
| assets/index-CVFbAi7m.js | 7d6125b29cfe6f37040c601998e6e2c5d2782e3bd6680ae5d1a3caf3e4b96443 |

The lint migration was checked against the official [ESLint 10 migration guide](https://eslint.org/docs/latest/use/migrate-to-10.0.0).
Build command: `npm run build --prefix web`; static output: `web/dist/`, base `/errorbars/`.
No hosting verification is claimed for these local changes.

| Local Beads ticket | Work |
| --- | --- |
| officina-4nv | Equal-weight question summaries and repeat counts |
| officina-rdi | Validated paired inference and independent cluster counts |
| officina-ixs | Unambiguous input and consistent cluster metadata |
| officina-0rv | Missing/unsupported Inspect grades |
| officina-5j7 | Bounded bootstrap working memory |
| officina-17q | Supported browser lint tooling |
| officina-xpk | Unavailable pairing diagnostics and nullable exports |

Tracking is in Officina's local/stealth workspace and is explicitly exported to its
ignored `.beads/issues.jsonl`. No public issue or release was created.

## Remaining limits

Question averages and their intervals assume an appropriate independently sampled question
set, or enough independent clusters for the clustered estimate. CLT and percentile bootstrap
intervals are approximate; two questions do not support a reliable population decision.
Per-model leaderboard intervals remain unclustered, while pairwise grouping uses clustered
p-values when applicable. No failure to reject establishes model equivalence.

Input validation cannot establish that two harness runs actually used identical question
contents from IDs alone. Domain/task namespaces, missing planned questions and an explicitly
chosen cohort remain the caller's responsibility. Variance components in squared units below
float64 representability are refused rather than reported as zero. Browser checks cover
Chromium and Firefox, not Safari or physical mobile devices.
