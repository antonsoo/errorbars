# Large binary comparisons without giant integer tails

The baseline source, `0590c884ea168530c2831aa97ff1f78c48eebca6`, evaluates
an exact McNemar test by updating almost one binomial coefficient per discordant
pair. Those integers grow with the number of observations. A near-balanced
200,000-disagreement comparison took a median 2.306 seconds in the retained
sequential capture. Leaderboards repeat the calculation for every model pair.

The new evaluation uses the same finite binomial distribution. It does not
substitute a normal or chi-square approximation. It also avoids two redundant
validation passes in the CLI/leaderboard path. Public loading and analysis still
validate their inputs on every call, including after a caller mutates an
`EvalData`; there is no saved validation flag.

## Probability evaluation

If `b` and `c` count the two directions of disagreement, set `n = b+c` and
`k = min(b,c)`. The two-sided p-value is `min(1, 2*P(X <= k))` for
`X ~ Binomial(n, 1/2)`. This is the same test used before this change.
See the [SciPy binomial probability definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binom.html)
and [binomial-test API](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html).

The central probability for even `n=2m` is a product of `(2i-1)/(2i)` for
`i=1..m`. The odd case follows from the adjacent binomial coefficient. From
there, the recurrence `P(X=i-1)/P(X=i) = i/(n-i+1)` moves toward the selected
tail. Intermediate masses are rescaled by powers of two before underflow.
`math.fsum` sums tail probabilities relative to their largest term; the binary
scale is applied after doubling the complete tail. This uses linear work in the
number of observations and avoids arithmetic on observation-sized integers.

One numerical boundary also improves: 1,075 disagreements all in one direction
have a two-sided probability of `2^-1074`, the smallest positive binary64 value.
The earlier code rounded the one-sided tail to zero before doubling. The
current CLI, standalone report and JSON download retain `5e-324`.

## Actual workload, not just a kernel timer

`generate.py` creates eight independent random binary runs over 200,000
questions: 1,600,000 CSV observations and 28 comparisons. This is a **synthetic
throughput control**, not model output or an accuracy benchmark. The committed
[input receipt](results/input.json) records its generator, seed, successes,
discordance counts, byte length and SHA-256. The 28.8 MB CSV is generated into
the ignored `cache/` directory rather than committed.

```text
CSV -> load and validate -> question means -> paired tests -> Holm and ranks
                             ^                  ^
                       reuse checked rows   normalized tail
```

The [sequential baseline](results/serial-before.json) and
[sequential current capture](results/serial-after.json) retain the complete
CLI reports as well as three raw timing samples per comparison size. For
200,000 disagreements, kernel median time changes from 2.306 seconds to
0.01264 seconds. This is a comparison-kernel result, not an end-to-end CLI
speedup claim.

The first sequential full-CSV captures were 50.06 seconds before and 70.20
seconds after; these measurements do **not** establish a full CLI speedup.
The two repeated serial pairs additionally record user/system CPU time and
peak resident memory:

| Serial pair | Baseline wall | Current wall | Baseline CPU | Current CPU |
|---|---:|---:|---:|---:|
| 1 | 125.77 s | 55.12 s | 94.71 s | 51.52 s |
| 2 | 73.35 s | 56.66 s | 72.99 s | 53.59 s |

The [summary](results/summary.json) records both pairs; each
`repeated-before-N.json` / `repeated-after-N.json` retains its own complete
report filename and CPU/RSS counters. These runs show less CPU work under this
control, with import, validation and question alignment still material costs.
This is a shared WSL2 Linux host; scheduling and other activity are not
controlled. No universal end-to-end speedup is established.

The [instrumented profile](results/profile.json) of 400,000 rows identified
12 validation calls: four whole-dataset passes plus one per-model pass over
all rows in aggregate. The final code removes the CLI wrapper's duplicate
pass and the revalidation of filtered, just-validated model rows. It retains
the public loader, concatenation and analysis checks. Means still use the
same score lists and summation, preserving repeated-generation behavior.
Profile times are attribution measurements with profiler overhead.

## Correctness and retained limits

- [4,368 probability checks](results/oracles.json) compare against complete
  integer-rational tails for small/boundary counts and SciPy for larger counts
  through one million disagreements. Agreement uses `2e-11` relative tolerance,
  with four smallest-subnormal units of absolute tolerance at underflow.
  This is numerical evaluation of the exact distribution, not exact arithmetic.
- The receipt separately records cases where the installed SciPy 1.18.1 returns
  zero despite a representable positive rational answer. Those boundary cases
  use the complete integer numerator as their oracle; the SciPy result is not
  silently treated as ground truth.
- Whole-CSV comparisons retain model estimates, intervals, selected test names,
  Holm decisions, groups and rank sets. Only floating-point tail values can
  differ within the stated tolerance.
- The [retained SWE-bench audit](results/swe-audit.json) checks the public
  leaderboard API on 173 submissions and 500 tasks, retaining the earlier
  study's exclusions. All 14,878 raw and Holm-corrected exact p-values agree
  with complete integer-combination tails; no significance decision changes.
  The maximum absolute raw-p difference is `8.88e-16`. This is a diagnostic
  under task independence, not an assertion that SWE-bench tasks are independent.
- Missing cohorts, repeated generations, grouped questions, scoring conflicts
  and mutation after analysis keep their existing validation/inference policies.
  The browser calculator's separate fixed SWE-bench implementation is unchanged.
- Runtime dependencies remain NumPy alone. The study's independent references
  use development dependencies; timing scripts use Linux's `resource` module.

## Installed artifacts and offline review

The [verification receipt](results/verification.json) records the clean Python
3.14 environment (788 checks), clean web build (691 checks), production app
workflows (52), and installed-wheel standalone report workflows (38). Chromium
and Firefox open the reports in fresh contexts with networking already disabled.
The smallest positive tail survives the complete JSON download, and the final
question remains inspectable and exportable as CSV. The
[Chromium](results/chromium-report.json) and
[Firefox](results/firefox-report.json) observations retain those values.

The four inspected captures show the installed report after searching for the
last question and opening its evidence:

| Engine | Desktop | 375 px |
|---|---|---|
| Chromium | [Capture](../../docs/assets/mcnemar-throughput/chromium-1440.png) | [Capture](../../docs/assets/mcnemar-throughput/chromium-375.png) |
| Firefox | [Capture](../../docs/assets/mcnemar-throughput/firefox-1440.png) | [Capture](../../docs/assets/mcnemar-throughput/firefox-375.png) |

A wheel rebuilt from the source distribution matches all 28 package files in
the workspace; [artifact hashes and comparisons](results/artifacts.json) retain
that boundary. A bare Python 3.14 wheel installation, with NumPy as its only
runtime dependency, replays the full CSV with unchanged pair decisions and
ranks. This installation replay ran alongside other checks and is used only
for correctness, not timing. Python 3.10 with the declared NumPy 1.24 floor
passes 147 focused checks; 15 optional Inspect AI checks skip because that
package is absent. The complete clean environment has no skips.

These results describe this source change and its locally built artifacts.
They do not establish a package release or hosted deployment.

## Reproduce

From the repository root:

```sh
uv sync --locked --group dev --extra all
uv run python studies/mcnemar-throughput/generate.py
uv run python studies/mcnemar-throughput/benchmark.py current
```

To compare with the old code using the same interpreter and dependencies,
extract the baseline revision and point `PYTHONPATH` at that archive's `src/`
when invoking the same benchmark script. Run baseline and current captures
sequentially; keep wall and CPU measurements together. `--cli-only` avoids
repeating the kernel measurement, and `--kernel-only` skips the full CSV.

```sh
uv run python studies/mcnemar-throughput/oracles.py
uv run python studies/mcnemar-throughput/audit_swe.py
```

Build with `uv build`; the wheel includes the offline comparison-report assets.
Browser checks use `ERRORBARS_REPORT_PYTHON` to select a separately installed
wheel and disconnect before opening each standalone report:

```sh
cd web
ERRORBARS_REPORT_PYTHON=/path/to/installed/bin/python npm run test:reports
```

No model is called and no evaluation data are uploaded by these workflows.
