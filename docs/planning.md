# Evaluation planning

The web calculator plans a single paired comparison: each model answers the
same distinct questions once. It estimates either the question count needed
for a target accuracy improvement or the detectable gap at a fixed question
budget. The Python CLI supplies both directions through `errorbars power`.

## Inputs and results

| Editor | Units | Browser range |
| --- | --- | --- |
| Baseline accuracy | Percent | 0.1 to 99.9 |
| Gap to detect | Percentage points | 0.01 to 50, subject to baseline + gap <= 100% |
| Available questions | Distinct questions per model | Integers from 2 to 1,000,000,000 |
| Paired correlation | Correlation of the models' scores on shared questions | -0.95 to 0.95 |
| Average cluster size | Questions per group | 1 to 1,000; fractions are allowed |
| Intraclass correlation | Correlation within a group | 0 to 1 |
| Significance level | Percent, two-sided | 0.1 to 20 |
| Target power | Percent | 50 to 99.9 |

Number fields retain the precision entered; sliders provide convenient
adjustment within their steps. Moving a slider replaces that input with the
slider's value. Switching modes preserves both draft inputs and uses only
the active one. Invalid active inputs hide the result and disable downloads
until corrected. An impossible requested improvement is explained without
silently changing the request. Reset restores all defaults and the
questions-needed mode.

A 50% baseline, a 3-point gap, correlation 0.3, alpha 5%, power 80%, and no
clustering produce **3,053 questions per model**: **6,106 model answers**.
At correlation 0, the same plan needs **4,361 questions per model**. This
comparison changes only the pairing assumption; it does not estimate the
correlation from data.

The budget table and curve use the actual computed MDE at integer question
counts. The marker therefore may be slightly below the requested gap after
rounding the required count upward. Every plotted point is calculated; there
is no simulated scatter or confidence band. Axis labels retain their size
when the viewport changes. A fixed link on small screens gives the current
answer and jumps to the result, or to the invalid field that needs correction.

## Save and reproduce

Download plan creates `errorbars-plan.json`. No input data file is required,
and the artifact contains no observed evaluation scores.

| JSON field | Meaning |
| --- | --- |
| `format`, `schemaVersion` | `errorbars-plan`, version `1` |
| `method` | `paired-normal-approximation-v1` |
| `mode` | `questions` or `budget` |
| `inputs` | Baseline, alpha, power, rho, one sample per question, cluster assumptions, derived design effect, and the active gap or budget |
| `result` | Question count, actual MDE, upper bound on improvement, whether the MDE fits that upper bound, model-answer count, approximate groups, variance |
| `sensitivity` | Result with rho=0 and every other assumption held fixed |
| `units` | Accuracy and differences are fractions; multiply differences by 100 for percentage points |
| `assumptions`, `warnings` | Model caveats and conditions affecting this specific plan |
| `cliCommand` | A complete `errorbars power ... --json` command |
| `generatedAt` | ISO timestamp of the download |

The inactive gap or budget is `null`, so an old draft cannot be mistaken for
an applied parameter. In questions mode the sensitivity's MDE is evaluated
at its own required count; in budget mode it uses the shared fixed budget.
The JSON does not provide a plan-import workflow.

Open **Reproduce this plan** and use **Select command** to select the complete
command for ordinary keyboard copying. This does not need clipboard API
permissions. The browser uses Wichura's AS241 inverse-normal algorithm, adapted from CPython
and checked against independent SciPy quantiles. Values agree with Python to the
tested numerical tolerance, rather than necessarily bit for bit. Integer counts extremely close to a rounding boundary
can differ by one across floating-point implementations.

Calculations and downloads work offline after the page has loaded. Reloading
the page requires the site files again. Only the theme preference is stored;
plans are not persisted in browser storage or in the URL. Download a plan
before leaving the page if you need to keep it.

## Limits of the model

This is the existing equal-variance normal approximation documented in
[formulas.md, section 11](formulas.md#11-power-analysis), not an exact paired
binary power calculation. It assumes `p(1-p)` for both models. The correlation
and ICC are planning assumptions. It does not enforce the joint Bernoulli
constraints relating correlation to two different accuracies.

A result below 30 questions, or fewer than 30 approximate groups when
clustering is enabled, carries a warning. These thresholds are reminders to
validate the design, not validated sample-size cutoffs. A plan above them
can still be unreliable near accuracy boundaries or with unusual grouping.
Unequal cluster sizes and few independent groups can require a different
analysis. The displayed group count is approximate and is not rounded into
a recruitment recommendation. Budget mode retains an MDE beyond the possible
improvement to 100% and flags it explicitly.

The page uses one answer per model per question. Python and CLI plans with
multiple answers now require an explicit within-question repeat correlation;
the [repeated-answer workflow](repeated-planning.md) explains the variance floor
and the distinct meanings of repeat and pairing correlation. The TypeScript
formula API enforces the same rule. Multiple model comparisons also need a
separate multiplicity plan.

## Interface direction

The planner extends the existing scientific instrument layout: exact controls
on the left, calculated evidence on the right, stacked on a phone. The retained
palette is paper `#f2f3ee`, surface `#ffffff`, ink `#14181c`, muted ink `#5b6169`,
signal blue `#2454a6`, and warning amber `#a85f22`, with existing dark equivalents.
Spectral carries the headings, IBM Plex Sans the controls, and IBM Plex Mono
the numeric evidence. All fonts are local. The curve and its numeric budget
table carry the visual emphasis; borders group controls and results, and
warnings appear only when they change how a plan should be interpreted.
