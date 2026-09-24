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
(`leaderboard.build_leaderboard`'s `use_wilson_below_n`), and CLT
otherwise; you can force either with `--ci`. Verified against
`statsmodels.stats.proportion.proportion_confint(method="wilson")` to
1e-9 (`tests/test_stats_vs_oracles.py`) and by Monte Carlo coverage
(`tests/test_coverage_montecarlo.py`) which also shows the Wald interval
under-covering at $p=0.05, n=30$ while Wilson stays near nominal.

## 3. Bootstrap interval

Percentile bootstrap: resample $n$ scores with replacement $B$ times
(default $B=10{,}000$), take the mean of each resample, and report the
$[\alpha/2, 1-\alpha/2]$ empirical quantiles of the resample means. Useful
as a model-free cross-check, and for statistics with no closed-form SE.

## 4. Cluster-robust standard error

When questions are grouped (e.g. several questions per reading passage),
scores within a cluster are correlated, so treating all $n$ questions as
independent understates the true SE. The standard fix is the CR1 cluster
sandwich estimator (as if regressing $y$ on a constant with cluster-robust
covariance): let $e_i = y_i - \bar{y}$ and let $u_g = \sum_{i \in g} e_i$
be the summed residual in cluster $g$ (of $G$ clusters). Then

$$\widehat{\mathrm{Var}}(\bar y) = \frac{G}{G-1}\cdot\frac{1}{n^2}\sum_{g=1}^{G} u_g^2,$$

which is exactly `statsmodels`' `OLS(y, const).fit(cov_type="cluster")`
with its default small-sample correction $\frac{G}{G-1}\cdot\frac{n-1}{n-K}$
(here $K=1$ parameter, the constant, so $\frac{n-1}{n-K}=1$ and only the
$G/(G-1)$ term remains). Reference: MacKinnon & White (1985); Cameron,
Gelbach & Miller (2011), "Robust Inference with Multiway Clustering."
Verified to match `statsmodels` to 1e-9 for both balanced and unbalanced
cluster sizes (`tests/test_stats_vs_oracles.py`), and its 95% CI is shown
by simulation to cover the true mean close to 95% of the time on clustered
data where the naive (non-clustered) interval would under-cover
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

## 7. Paired comparison

For two models scored on the *same* questions, the difference
$d_i = a_i - b_i$ has mean $\bar d$ and SE $s_d/\sqrt n$ — a paired t-test.
`errorbars` reports the two-sided p-value from the normal approximation
$Z = \bar d / \mathrm{SE}(\bar d)$ (matches `scipy.stats.ttest_rel`'s
t-distribution p-value closely once $n \gtrsim 30$; for very small $n$ the
t-distribution is more exact, but we avoid a scipy runtime dependency).

**Why pairing helps.** For two *independent* samples of size $n$,
$\mathrm{Var}(\bar a - \bar b) = \frac{\sigma_a^2 + \sigma_b^2}{n}$. For a
*paired* design, $\mathrm{Var}(\bar d) = \frac{\sigma_a^2 + \sigma_b^2 -
2\rho\sigma_a\sigma_b}{n}$ where $\rho$ is the correlation between the two
models' per-question scores. Because harder questions are harder for every
model, $\rho > 0$ in practice, so pairing shrinks the SE — we report this
as `variance_reduction` $= 1 - \mathrm{SE}_\text{paired}^2 /
\mathrm{SE}_\text{unpaired}^2$.

When `clusters` are supplied, the same cluster-robust SE from §4 is applied
to the difference series $d_i$, giving a clustered paired SE/CI/p-value —
this is what `leaderboard` uses for significance when cluster data is
available, since ignoring clustering here has the same under-coverage
problem as for a single mean.

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
