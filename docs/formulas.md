# Formulas and derivations

This document derives every statistic `errorbars` computes. Notation:
$n$ questions, scores $y_1, \dots, y_n$, mean $\bar{y}$, sample variance
$s^2 = \frac{1}{n-1}\sum_i (y_i - \bar{y})^2$. Where we cite an external
result we give the reference; everything else is standard inferential
statistics assembled for the eval setting described in Evan Miller,
["Adding Error Bars to Evals: A Statistical Approach to Language Model
Evaluations"](https://arxiv.org/abs/2411.00640) (arXiv:2411.00640, 2024).

## 1. CLT confidence interval for a mean

By the central limit theorem, $\bar{y}$ is approximately normal with
standard error $\mathrm{SE} = s/\sqrt{n}$. A $100(1-\alpha)\%$ CI is

$$\bar{y} \pm z_{\alpha/2} \cdot \mathrm{SE}, \qquad z_{\alpha/2} = \Phi^{-1}(1 - \alpha/2).$$

Implementation: `stats.mean_ci_clt`, `z_for_confidence` (via
`statistics.NormalDist.inv_cdf`, no scipy needed).

## 2. Wilson score interval

For a binary score, the Wald interval above ($\hat p \pm z\sqrt{\hat
p(1-\hat p)/n}$) can extend outside $[0,1]$ and under-covers badly when
$n$ is small or $\hat p$ is near 0 or 1. The Wilson (1927) interval
inverts the normal approximation to the *score* statistic instead of the
Wald statistic, which keeps it inside $[0,1]$ and gives much closer to
nominal coverage at small $n$:

$$\frac{\hat p + \frac{z^2}{2n} \pm z\sqrt{\frac{\hat p(1-\hat p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}.$$

`errorbars` uses Wilson by default for binary scores with $n < 30$
(`leaderboard.build_leaderboard`'s `use_wilson_below_n`) or with fewer than
10 successes or failures, where the CLT interval can leave $[0,1]$ at any $n$
(2 correct of 500 gives $[-0.0015, 0.0095]$), and CLT otherwise; you can
force either with `--ci`. Verified against
`statsmodels.stats.proportion.proportion_confint(method="wilson")` to
1e-9 (`tests/test_stats_vs_oracles.py`) and by Monte Carlo coverage
(`tests/test_coverage_montecarlo.py`) which also shows the Wald interval
under-covering at $p=0.05, n=30$ while Wilson stays near nominal.

## 3. Bootstrap interval

Percentile bootstrap: resample $n$ scores with replacement $B$ times
(default $B=10{,}000$), take the mean of each resample, and report the
$[\alpha/2, 1-\alpha/2]$ empirical quantiles of the resample means. Useful
as a model-free cross-check, and for statistics with no closed-form SE.

Resampling is batched with at most 250,000 temporary indices per batch when a single
resample fits that budget; larger inputs still require one complete resample. All $B$
means are retained for the percentile calculation, so working memory is $O(n+B)$ rather
than $O(nB)$. The random generator's state continues across batches, preserving the
same seeded draws and percentile result. The configured resample count must be an
integer of at least two, since one draw cannot estimate a bootstrap standard error.

## 4. Cluster-robust standard error

When questions are grouped (several questions per reading passage, several
tasks per repository), scores within a cluster are correlated, so treating all
$n$ questions as independent understates the true SE. Let $e_i = y_i - \bar{y}$,
let $u_g = \sum_{i \in g} e_i$ be the summed residual in cluster $g$ (of $G$
clusters), and let $n_g$ be its size.

**The estimator.** `errorbars` uses the bias-reduced CR2 sandwich estimator of
Bell & McCaffrey (2002), which for a mean is

$$\widehat{\mathrm{Var}}(\bar y) = \frac{1}{n^2}\sum_{g=1}^{G} \frac{u_g^2}{1 - n_g/n}.$$

The general CR2 form multiplies each cluster's residuals by
$(I - H_{gg})^{-1/2}$, where $H$ is the hat matrix. For a mean $H = \mathbf{1}\mathbf{1}'/n$,
so that adjustment scales a cluster's residual *sum* by $(1 - n_g/n)^{-1/2}$.
It undoes a mechanical bias: residuals sum to zero over the whole sample, so a
cluster that holds much of the data has its own sum pulled toward zero by the
mean it dominates. With independent questions
$E[u_g^2] = \sigma^2 n_g (1 - n_g/n)$, and dividing by $1 - n_g/n$ makes the
estimator unbiased whatever the cluster sizes.

**Its reference distribution.** The estimate is a quadratic form in the scores,
$\sum_g (a_g' y)^2$. Matching its first two moments to a scaled chi-square
(Satterthwaite) gives degrees of freedom $(\sum \lambda_j)^2 / \sum \lambda_j^2$
for the eigenvalues $\lambda_j$ of the Gram matrix of the $a_g$ (Bell &
McCaffrey 2002; Imbens & Kolesár 2016; Pustejovsky & Tipton 2018). For a mean,
with independent equal-variance questions as the working model, that matrix has
entries $\sqrt{c_g c_h}\,(n_g \delta_{gh} - n_g n_h / n)$ with
$c_g = 1/(1 - n_g/n)$, and the degrees of freedom reduce to

$$\nu = \frac{n^2}{\sum_g n_g^2 + \dfrac{\bigl(\sum_g c_g n_g^2\bigr)^2 - \sum_g c_g^2 n_g^4}{n^2}}.$$

The interval is $\bar y \pm t_{\nu,\,\alpha/2}\,\mathrm{SE}$. $\nu$ depends only on the
cluster sizes. Equal sizes give exactly $G - 1$ (40 clusters: a critical value
of 2.023 rather than 1.960). Unequal sizes give fewer: SWE-bench Verified's 12
repositories, one of which holds 231 of the 500 tasks, give $\nu = 3.33$ and a
critical value of 3.01. `summarize` and `compare` print $\nu$, and `compare`
adds a note when it is below 10.

**Why not the usual estimator.** Most packages report CR1,

$$\widehat{\mathrm{Var}}_{\mathrm{CR1}}(\bar y) = \frac{G}{G-1}\cdot\frac{1}{n^2}\sum_{g=1}^{G} u_g^2,$$

read against $t_{G-1}$ (`statsmodels`' `OLS(y, const).fit(cov_type="cluster")`;
MacKinnon & White 1985; Cameron & Miller 2015). With equal cluster sizes CR1 and
CR2 are the same number and $\nu = G - 1$, so nothing changes. With unequal
sizes CR1 is biased downward (by 19% on the SWE-bench Verified sizes, when
questions are independent) and $G - 1$ overstates how much the estimate rests
on. Simulated on those sizes with no true difference, a nominal 5% test rejects
9.7% of the time with CR1 and 3.0% with CR2 and $\nu$; with a 4-point spread of
true per-repository differences, 13.9% and 4.4%
(`studies/swe-bench-verified/analyze.py`, 20,000 draws each;
`tests/test_few_clusters.py` holds a smaller version of the same check).
`errorbars` used CR1 through version 0.2.4. `cluster_robust_se(..., kind="CR1")`
still computes it, for comparison with other software.

**Checks.** The closed forms above agree to 1e-9 with the general matrix
definitions evaluated independently (`tests/oracles.py`) on random unequal
clusters; CR1 matches `statsmodels` to 1e-9 (`tests/test_stats_vs_oracles.py`);
and the 95% interval covers the true mean close to 95% of the time on clustered
data where the unclustered interval under-covers
(`tests/test_coverage_montecarlo.py`).

## 5. Intraclass correlation (ICC) and design effect

The one-way random-effects ANOVA estimator (Fisher; Kish 1965, eq.
8.4.1) decomposes total sum of squares into between-cluster ($SSB$) and
within-cluster ($SSW$) parts:

$$MSB = \frac{SSB}{G-1}, \quad MSW = \frac{SSW}{n-G}, \quad
k_0 = \frac{n - \sum_g n_g^2/n}{G-1},$$

$$\widehat{\mathrm{ICC}} = \frac{MSB - MSW}{MSB + (k_0-1)MSW}.$$

$k_0$ reduces to the common cluster size when clusters are balanced. Kish's
design effect is then $\mathrm{DEFF} = 1 + (\bar m - 1)\cdot\mathrm{ICC}$
where $\bar m$ is the average cluster size — the factor by which the
variance of the mean is inflated relative to simple random sampling of the
same $n$. `summarize` reports both alongside the cluster-robust SE so you
can see *why* the interval widened.

## 6. Within/between-question variance decomposition

When a question is sampled $k$ times (repeated generations), the observed
variance across all samples mixes two sources: item difficulty (variance
*between* questions) and decoding/sampling noise (variance *within* a
question's repeated samples). Using the same one-way random-effects moment
estimator as §5 but grouping by `question_id` instead of `cluster_id`:

$$\widehat{\sigma}^2_{\text{within}} = MSW, \qquad
\widehat{\sigma}^2_{\text{between}} = \max\!\left(0, \frac{MSB - MSW}{k_0}\right).$$

This tells you whether more samples per question (reduces
$\sigma^2_{\text{within}}/k$) or more questions (reduces
$\sigma^2_{\text{between}}/n$) would tighten your estimate more — the
paper's central point about where to spend a fixed compute budget.
Recovery of known simulated components is checked in
`tests/test_within_between.py`.

The CLI and leaderboard average repeated generations within each question, then apply
mean/paired estimators to the question averages. This gives each question weight $1/n$,
even with unequal generation counts. `n` is the number of distinct questions and
`n_observations` preserves the number of draws. Within/between decomposition continues to
use the raw draws; clustered SE uses one averaged score and one cluster assignment per
question. Wilson is reserved for one binary observation per question. More draws can
reduce sampling noise, but they do not create more independently sampled questions.

## 7. Paired comparison

For two models scored on the *same* questions, the difference
$d_i = a_i - b_i$ has mean $\bar d$ and SE $s_d/\sqrt n$ — a paired t-test.
`errorbars` reports the two-sided p-value of $T = \bar d / \mathrm{SE}(\bar d)$
under Student's t with $n - 1$ degrees of freedom, and the interval
$\bar d \pm t_{n-1,\,\alpha/2}\,\mathrm{SE}$, matching `scipy.stats.ttest_rel`
to 1e-7 at every $n$ (`tests/test_compare_vs_oracles.py`). The t tail comes
from the regularized incomplete beta function, $P(|T| \ge t) =
I_{\nu/(\nu+t^2)}(\nu/2, 1/2)$, evaluated by continued fraction, so there is
still no scipy at runtime. (The normal approximation this replaced was
anti-conservative for small $n$: at 8 degrees of freedom, $T = 2.2$ is
$p = 0.028$ under the normal but $0.059$ under t.)

For exactly constant differences the variance estimate is zero: a nonzero difference
uses the $|T|\to\infty$, p=0 limit (also returned by SciPy), while identical scores use
p=1 by explicit convention (SciPy returns NaN for 0/0). Warnings accompany either
case; a collapsed interval is not evidence of population certainty. For binary pairs,
the exact McNemar result is retained separately. These conventions also apply to
zero cluster-sum variance. A single cluster is rejected because it carries no
information about variation between clusters; it is not replaced with an
independent-observation SE.

Score vectors and group identifiers must be finite, one-dimensional and aligned.
Binary means exactly 0 or 1. SEs, correlation and paired variance reduction are computed
on rescaled scores before restoring their units; directly squaring scores near
$10^{-200}$ would underflow, changing the test result when only the score units changed.

Pearson correlation is undefined when either vector has zero variance. Likewise,
`variance_reduction` is undefined when both vectors are constant, since the unpaired
variance denominator is zero. These fields return `None`/JSON null with warnings, and the
CLI shows `unavailable`. They are not assigned a fabricated zero; ordinary mean/difference
and test outputs remain available under the zero-variance conventions above.

**Why pairing helps.** For two *independent* samples of size $n$,
$\mathrm{Var}(\bar a - \bar b) = \frac{\sigma_a^2 + \sigma_b^2}{n}$. For a
*paired* design, $\mathrm{Var}(\bar d) = \frac{\sigma_a^2 + \sigma_b^2 -
2\rho\sigma_a\sigma_b}{n}$ where $\rho$ is the correlation between the two
models' per-question scores. Because harder questions are harder for every
model, $\rho > 0$ in practice, so pairing shrinks the SE — we report this
as `variance_reduction` $= 1 - \mathrm{SE}_\text{paired}^2 /
\mathrm{SE}_\text{unpaired}^2$.

When `clusters` are supplied, the same cluster-robust SE from §4 is applied
to the difference series $d_i$, giving a clustered paired SE/CI/p-value on
t with the degrees of freedom $\nu$ of §4 —
this is what `leaderboard` uses for significance when cluster data is
available, since ignoring clustering here has the same under-coverage
problem as for a single mean. The two tests answer different questions:
the unclustered one is about more questions like these from the same
clusters, the clustered one about new clusters. With few or very unequal
clusters the second has little to work with and says so through $\nu$.

## 8. McNemar's exact test

For paired binary outcomes, only the *discordant* pairs matter: $b$ =
(A wrong, B right), $c$ = (A right, B wrong). Under the null that A and B
are equally likely to be the one that's right when they disagree,
$b \sim \mathrm{Binomial}(b+c, 0.5)$. The exact two-sided p-value sums the
binomial tail at or below $\min(b,c)$ and doubles it (McNemar 1947).
Verified against `statsmodels.stats.contingency_tables.mcnemar(exact=True)`
to 1e-9.

## 9. Holm-Bonferroni correction

Controls the family-wise error rate across $m$ pairwise tests without
assuming independence (Holm, 1979), less conservative than Bonferroni:
sort p-values ascending, adjust the $k$-th smallest to
$\max_{j \le k}\left[(m-j+1)\cdot p_{(j)}\right]$ capped at 1. Verified
against `statsmodels.stats.multitest.multipletests(method="holm")`.

## 10. Grouping indistinguishable models

Build a graph where models are nodes and an edge connects two models whose
Holm-adjusted pairwise p-value is $\ge \alpha$ (not significantly
different). The maximal cliques of this graph (Bron–Kerbosch, no pivoting
— the leaderboard sizes this targets are small enough that this is fast)
are the groups reported: every model in a clique is pairwise
indistinguishable from every other model in that clique. This is the
standard "compact letter display" idea (cf. `multcompView` in R), applied
directly rather than via a minimal-letters heuristic, so a model can
legitimately belong to more than one group.

## 11. Power analysis

**Model.** A single sample of a question has variance $V_1 = p(1-p)$ for a
binary metric at baseline accuracy $p$ (or a user-supplied `variance` for a
continuous one). Averaging $k$ repeated samples per question reduces that
to $V = V_1 / k$ (see caveat below). Pairing two models with per-question
correlation $\rho$ gives $\mathrm{Var}(\text{diff}) = 2V(1-\rho)$ instead of
$2V$ for an unpaired design (§7). Clustering multiplies by the design
effect from §5: $\mathrm{Var}(\text{diff}) = 2V(1-\rho)\cdot\mathrm{DEFF}$.

**Sample size.** For a two-sided test at level $\alpha$ and power
$1-\beta$ to detect difference $\delta$:

$$n = \frac{(z_{\alpha/2} + z_\beta)^2 \cdot 2V(1-\rho)\cdot\mathrm{DEFF}}{\delta^2}.$$

**Minimum detectable effect** for a given $n$ is the same formula solved
for $\delta$:

$$\delta_{\text{MDE}} = (z_{\alpha/2} + z_\beta)\sqrt{\frac{2V(1-\rho)\cdot\mathrm{DEFF}}{n}}.$$

This is the standard normal-approximation two-sample power formula (e.g.
Fleiss, Levin & Paik, *Statistical Methods for Rates and Proportions*, 3rd
ed., ch. 3) generalized with the pairing and clustering factors above.
Checked by simulation in `tests/test_power.py`: for several
$(V, \rho, \delta)$ combinations, running the paired z-test on simulated
correlated-normal data at the computed $n$ recovers the target power to
within Monte Carlo error, and $n$ scales linearly in the design effect and
inversely in samples-per-question as the formula predicts.

**Caveat on samples-per-question.** This planning formula assumes all
per-sample variance is "within-question" (decoding noise), so more samples
per question always shrinks $V$ by a factor of $k$. In reality some of
$p(1-p)$ is genuine item-difficulty variance (§6), which extra samples of
the *same* questions cannot reduce. Treat the $k>1$ case as an optimistic
planning assumption; for a **post-hoc** measurement with the true
within/between split, use `summarize` with a `sample` column instead.

**Input and numeric domain.** Both planning directions require finite inputs.
Question and repeated-sample counts must be integral and between their minimum
(2 questions or 1 sample) and `2**53 - 1`, so saved plans remain exactly
representable in the browser. The sum of the two normal quantiles must be
positive; very low power requests at or below the positive-effect approximation's
boundary are rejected rather than returning a negative detectable difference.
An unrepresentable question count or effect raises a validation error.
The two-sided critical value uses the lower tail `-Phi^-1(alpha/2)` to avoid
rounding `1 - alpha` to 1 for small significance levels.

The browser restricts power to 50%-99.9% and alpha to 0.1%-20%. Its exact
editors, inverse budget mode, sensitivity calculation, and saved-plan units
are documented in [Evaluation planning](planning.md). A budget's mathematical
MDE can exceed `1 - baseline_accuracy`; this is retained and labelled as an
unachievable improvement rather than clipped into a plausible-looking result.
The warning thresholds of 30 questions or groups are prompts to check the
approximation, not guarantees of validity above those thresholds.
