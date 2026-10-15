# Identical answers, different recorded grading parameters

Five fresh **lm-eval 0.4.13** runs use 24 constructed local questions and
scripted answers. They are software reproductions, not measurements of a
trained model. No model weights, remote inference or external dataset is used.
The [native captures](captures/) are unedited evaluator and tracker output;
[`capture.py`](capture.py) is the exact generator.

On the published baseline `dfdc9ca`, the reader retained `exact_match` as a
metric name but discarded its recorded `ignore_case` argument. The built-in
case-sensitive and case-insensitive graders judged identical answers as
33.3% and 66.7% correct. Errorbars treated those grades as a model comparison:
the exact McNemar p-value was **0.0078125** despite no answer changing.

| Native pair | What changes | Baseline | Corrected source |
| --- | --- | --- | --- |
| strict / folded | Only `ignore_case` | -0.3333 difference; p = 0.0078125 | 24 conflicting grading declarations; inference and ranking withheld |
| strict / strict-repeat | Declaration key order | Zero difference; p = 1 | Same result, 24 matching recorded declarations |
| strict / prompt-variant | Prompt template | Zero difference; p = 1 | Same result, 24 matching recorded declarations |
| strict / improved-strict | Eight answers | -0.3333 difference; p = 0.0078125 | Same valid exact test under the common recorded grader |

The [before](results/before.json) and [after](results/after.json) retain library
cohorts, actual compare/leaderboard CLI exit states, raw-score exact-test
diagnostics and SHA-256/size receipts for all ten native files. The replay
checks documents, targets, answers and prompt arguments directly. The raw-score
p-value remains an explanation of the old failure, not an available model
comparison after a known grader conflict.

## What is checked

The reader fingerprints the selected declaration's forwarded grading kwargs
and its `hf_evaluate` backend choice, for the harness's default
`generate_until` scoring path. It uses the recorded task configuration in the
matching-timestamp results file, including with an explicit model name.
Key order does not change the fingerprint. Model names, prompt templates,
few-shot counts and generation settings do not enter it.

Aggregation and `higher_is_better` have separate checks; they do not alter the
per-item grades. In particular, finite `mean` and `nanmean` inputs retain their
existing supported behavior. Unrelated metric declarations do not enter the
selected metric's fingerprint. Contradictory duplicate selected declarations
or invalid recorded backend/parameter values stop the import.

The fingerprint uses the existing `ScoringRule.config_hash` field, so canonical
CSV, normalized JSONL/DataFrame data and standalone comparison evidence retain
it without a new output schema. Native and canonical comparisons both withhold
inference for conflicting known settings. The question ledger still retains
each observed score and source record; its complete JSON download keeps both
fingerprints. Raw grader parameters are not copied into reports or CSV exports,
and no grading code or regex from metadata is executed during import.

These checks concern **recorded settings**, not verified metric implementation
code. Explicit defaults and omitted defaults can conservatively differ unless
the reader normalizes them (the absent `hf_evaluate` flag means false in this
native path). Matching declarations do not authenticate a file or establish
identical plugin code, dependencies or unrecorded state.

## Unknown remains unknown

The metric kwargs are not used when a custom `process_results` function
overrides scoring. They also do not define the harness's other output-type
branches. Hashing those unused kwargs would certify the wrong evidence.
Such cases keep `config_hash=None` and explicitly unavailable grading checks.
Missing task configuration, output type or selected metric declaration also
keeps the definition unknown. Ordinary imports remain usable with that
limitation; absence is not a matching declaration.

This preserves the earlier [metric-selection study](../lm-eval-evidence/README.md):
its two custom processors return the same selected grades in different key
orders. They remain comparable under an explicit common metric, with their
grading definitions unchecked. The new guard does not attempt Python function
equivalence or hash the whole task configuration.

The pinned upstream [task implementation](https://github.com/EleutherAI/lm-evaluation-harness/blob/v0.4.13/lm_eval/api/task.py)
forwards metric kwargs on default generation scoring and bypasses them for
custom processors. The [metric implementation](https://github.com/EleutherAI/lm-evaluation-harness/blob/v0.4.13/lm_eval/api/metrics.py)
implements the built-in case-sensitive/case-insensitive exact match used here.

## Reproduce

Install the source checkout, then run the retained native inputs:

```bash
uv sync --locked --group dev --extra all
uv run python studies/lm-eval-grading/replay.py --out /tmp/grading-replay.json
uv run python studies/lm-eval-grading/verify.py --out /tmp/grading-workflows.json --artifacts /tmp/grading-artifacts
```

The second command retains all four comparisons and eight actual CLI runs.
The third runs 20 native/import/canonical compare and leaderboard workflows,
including existing-plot preservation on refusal. Both scripts need only the
package and NumPy, and can be run through a separately installed wheel's
interpreter from outside the checkout.

To regenerate logs, use a separate environment with `lm-eval==0.4.13` and run
`python capture.py --out /path/to/new-captures`. Package installation needs
network access; capture generation uses local data and scripted providers.
Do not append new timestamped runs into the retained capture directories.

The [installed-package verification](../../docs/verification-lm-eval-grading-2026-10-15.md)
retains clean archive, minimal-wheel and offline browser checks, including
actual downloaded evidence and inspected screenshots.
