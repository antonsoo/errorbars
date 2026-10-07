# The questions behind a paired score

The comparison report answers three questions that a mean and p-value leave open:
which questions changed, which questions did not enter the comparison, and whether
one passage accounts for much of the apparent gain. It is a local, self-contained
HTML file. All evidence and fonts are embedded; it can be opened without a server
or internet connection.

This feature is in the **unreleased source checkout**, not the published 0.2.4 package.

## Try it on retained model outputs

From the repository root:

```sh
uv sync --locked --no-dev
uv run --no-dev errorbars compare tests/fixtures/lm_eval_output \
  --model-a hf-internal-testing/tiny-random-gpt2 --model-b sshleifer/tiny-gpt2 \
  --html comparison.html
```

Open `comparison.html`. There is also a ready-to-open
[COPA comparison artifact](../examples/reports/copa-comparison.html).
Download that HTML file and open it locally.
For pip users, `pip install .` installs the checkout; the same `errorbars compare`
command works without `uv run --no-dev`. NumPy is the only runtime dependency.

These are two **real retained lm-eval 0.4.13 captures**, each covering 20 COPA
questions, already committed in `tests/fixtures/lm_eval_output/`. No new inference
calls were made for this report. The models are tiny test models; these results
are a demonstration of investigation, not a model recommendation.

| Observation | Value |
| --- | ---: |
| A: tiny-random-gpt2 mean | 0.8000 |
| B: tiny-gpt2 mean | 0.6000 |
| Mean A - B | +0.2000 |
| Paired 95% interval | [-0.0881, +0.4881] |
| Paired two-sided p-value | 0.1625 |
| A higher / B higher / equal | 6 / 2 / 12 |
| Shared IDs with matching content signatures | 20 |

Choose **B higher** and open `copa-15`. A scored 0; B scored 1. Both observations
point to record 16, line 16 of their respective source files, with the score key
`acc` and filter `none`. `copa-16` is the other lower score hidden by the aggregate
gain. Filtering these two cases does **not** rerun the test. The interval above
still describes all 20 shared questions and still contains zero.

![Question-level evidence on the real COPA captures](assets/comparison-evidence.png)

## Incomplete and repeated evaluations

The coverage table separates all questions in each input from the shared cohort.
All-question means can change simply because different questions were evaluated;
the paired estimate uses only shared IDs. Missing scores are not filled with zero.
Questions absent from both inputs cannot be discovered without an external roster.

The ledger retains the union of both question sets. Each side shows the question's
mean and its number of observations. Selecting it shows the actual samples or
epochs, scores and source locations. Sample labels do not pair individual
generations across runs: generations are averaged within each question and model,
then questions are weighted equally. Unequal sample counts therefore do not give
one question more votes.

An empty intersection, a single shared question or one independent cluster cannot
support the requested inference. With `--html`, the command writes an inspectable
report and **still exits nonzero**. It does not emit a successful numeric result
or invent an interval. Without `--html`, it reports the same inference error.

## Cluster sensitivity

```sh
uv run --no-dev errorbars compare examples/data/reading_comprehension.csv \
  --model-a tuned-70b --model-b baseline-70b --html clustered.html
```

This second dataset is **synthetic**. The mean difference is +0.0700 over 200
questions in 40 passages. The cluster-robust 95% interval is [-0.0199, +0.1599].
Omitting `passage-005` leaves a mean difference of +0.051282; that passage is the
largest absolute shift in this fixture. Click its name to inspect its five
questions. They retain their original scores and source locations.

For a cluster C with n_C questions and differences d_i:

```text
Full difference = sum(d_i) / n
Cluster contribution to the full difference = sum(d_i in C) / n
Difference without C = sum(d_i outside C) / (n - n_C)
Shift = difference without C - full difference
```

The deleted-cluster result is descriptive. No new p-value or confidence interval
is fitted to the selected subset. It is not a reason to remove an inconvenient
passage and then declare significance. Unequal cluster sizes retain equal weight
per question, not per cluster. Singleton-only groups do not need a separate
cluster-deletion table; the question ledger already exposes those contributions.

## Question identity

A reused question ID can conceal a changed document or reference answer. Native
lm-eval imports compute:

```text
question_hash = "lm-eval-doc-target-v1:" + SHA256(canonical JSON of {doc, target})
```

Canonical JSON here uses sorted object keys, ASCII escaping, compact separators
and finite JSON values. Object key order is ignored; string content, array order,
numeric serialization and target content are retained. This is an exact content
check, not a semantic-equivalence test or the RFC 8785 canonicalization scheme.
Prompt arguments, model responses and the log's own `doc_hash` are excluded.
An absent/empty document or absent/null target leaves the signature unavailable.

| Report state | Meaning |
| --- | --- |
| Matching | Both models provide the same signature for every observed generation of this question |
| Partial | Available signatures agree, but some repeated observations have no signature |
| Unavailable | At least one model has no known signature for this question |
| Conflicting | Known signatures differ; inference is withheld for the entire comparison |

CSV/JSONL can supply `question_hash`; `--question-hash-col` maps another column.
`errorbars import lm-eval ...` preserves native signatures in the canonical CSV.
Blank or absent hashes remain unknown; they never inherit another model's hash.
Different known hashes across generations of a single model/question are refused
before averaging. Inspect logs do not get automatic content hashes: their input
may itself be the prompt experiment, and there is no universal separate document
identity to assume.

On a conflict, inspect the two source records, confirm the dataset version,
reference answer and ID assignment, then correct the inputs or explicitly choose
the intended common cohort outside this report. Renumber genuinely different
questions so they cannot masquerade as a pair. There is no silent conflict-dropping
or ignore-conflicts switch. Equal hashes do not establish compatible scorers,
filters, dataset representativeness or trustworthy user-supplied signatures.

## Evidence, privacy and display limits

- **JSON** retains all questions and observations, source references, content
  signatures, comparison statistics, cohort counts, warnings and descriptive
  cluster sensitivity. It has `format: errorbars-comparison`, `schema_version: 1`.
  `comparison: null` and `unavailable_reason` represent withheld inference.
- **CSV** exports all questions matching the current filters, across every page.
  It includes the model names, mean scores, A - B difference, observation counts,
  coverage and identity state. Formula-like text cells are prefixed with an
  apostrophe; JSON preserves the exact original identifiers. Missing values stay
  blank. Scores are in their original units, not automatically percentages.
- The ledger renders at most 40 questions, 25 observations per selected side,
  and 12 clusters per page. The complete data stays in the artifact. Native
  file parsing, statistical calculations, serialization and browser JSON loading
  still require memory proportional to the full input. Paging is not a file-size
  or total-work limit.
- Source references are one-based record numbers and inclusive physical line
  ranges when available. Multiline CSV and skipped JSONL lines retain their
  locations; CSV ranges may include blank separators. Inspect uses sample record
  order plus the observed sample ID/epoch. Data constructed directly in Python
  can lack locations, which the report marks unavailable.
  After canonical CSV export and reimport, locations refer to that CSV. Generate
  the report directly from native logs to retain their original source locations.
- The report includes identifiers, score data, sample labels and source basenames.
  It omits raw prompts, responses and full source paths. Distinct files with the
  same basename get distinct source numbers. These exported identifiers and
  filenames can still be sensitive; omission of raw text is not anonymization.
- The artifact performs no network requests. A restrictive Content-Security-Policy
  admits only its exact embedded script/style hashes and data fonts. Imported
  labels render as text; control/bidirectional characters display as visible
  escapes. No theme or data is written to browser storage.
- Printed output shows the currently displayed pages and selected observations,
  with an explicit print note. Keep the HTML or JSON for the full evidence.

## Python use

```python
from errorbars.inputs import load_inputs
from errorbars.review import review_comparison
from errorbars.report import write_comparison_html

data = load_inputs(["tests/fixtures/lm_eval_output"]).data
review = review_comparison(data, "hf-internal-testing/tiny-random-gpt2", "sshleifer/tiny-gpt2")
write_comparison_html(review, "comparison.html")
evidence = review.as_dict()
```

`review_comparison` can return an unavailable comparison with a complete ledger;
check `review.comparison` before using inference. Writes replace the destination
atomically so a failed replacement leaves the previous report intact.

See [verification](verification-comparison-2026-10-07.md) for the real browser
workflows, independent calculations, wheel installation and measured limits.
