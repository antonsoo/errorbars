# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added

- `studies/swe-bench-verified/`: the package run over the per-task results of 173 public
  SWE-bench Verified submissions, with the scripts that fetch the data at a pinned commit and
  reproduce every number and figure. `to_csv.py` writes any submissions, or a run of your own,
  in the format `errorbars compare` reads.
- A second page on the site, `swe-bench.html`: pick any two of the 173 submissions, or paste a
  run of your own, and get the paired test, the repository-level test and a map of the 500
  tasks by repository. The TypeScript port of the comparison is tested against vectors this
  package computes on real pairs (`scripts/export_paired_vectors.py`).
- `cluster_degrees_of_freedom`, and `cluster_robust_se(..., kind="CR1")` for the classic
  estimator. `summarize` and `compare` print the clustered degrees of freedom; `compare` prints
  the clustered p-value and explains the result when fewer than 10 effective degrees of
  freedom carry it. JSON gains `clustered_dof`, `dof_clustered` and `n_clusters`.

### Changed

- lm-eval imports require `--metric` when selected records declare several metrics,
  validate that it is a declared score on every record, and refuse different metrics
  for shared questions across native input files. Model-name inference requires a
  results file with the samples' timestamp; renamed or orphaned samples need `NAME=PATH`
  or `--model`. This prevents metric-order changes from creating an apparent model
  improvement and unrelated results files from relabelling a run.
  [Actual harness capture and migration](studies/lm-eval-evidence/README.md).

- Standalone comparisons now share the leaderboard's data-based test selection.
  CLI and HTML headline exact McNemar for single binary observations, clustered t
  for grouped questions, and paired t for continuous or repeated means. JSON adds
  `inference`; existing p-value and interval fields keep their diagnostic meanings.
  No exact binary mean-difference interval is claimed. The SWE-bench browser also
  uses its exact task test: 102 of 14,878 unadjusted pairs change decision at 5%.
  [Counterexamples and independent replay](studies/comparison-inference/README.md).

- Leaderboard tables and SVGs show exact other-model rank sets instead of group
  letters or min-max tie spans. The old spans implied 150 false directed ties on
  the retained 173-submission SWE-bench board. JSON adds `rank_comparisons`,
  `untested_pairs` (with shared counts and reasons), and board-level `warnings`.
  Existing `groups`, tests and intervals are preserved. Comparisons with fewer
  than two shared questions remain explicitly untested. SVG labels wrap within
  the export instead of clipping. [Real-data audit](studies/leaderboard-ranks/README.md).

- Repeated-answer power plans require explicit `repeat_correlation` / `--repeat-correlation`
  for more than one answer per question. Python and TypeScript preserve between-question
  variance using `V * (r + (1-r)/k)`; single-answer plans are unchanged. JSON retains the
  supplied assumption (null if absent for one answer). Existing scripts relying on `V/k`
  must explicitly pass 0 if that independence assumption is intended.
  [Migration, simulations, and retained public outcomes](docs/repeated-planning.md).

- Leaderboard model intervals now honor supplied multi-question clusters, using CR2
  standard errors and effective-degree-of-freedom t critical values just like `summarize`.
  Tables and forest plots name their interval basis. JSON retains the unclustered estimate,
  confidence level, cluster count, degrees of freedom, and limitations. One cluster cannot
  silently yield an independent-question interval. Repeated generations keep equal question
  weighting. [Actual before/after intervals](docs/leaderboard-tests.md#confidence-intervals-also-honor-supplied-clusters).

- `leaderboard` selects exact McNemar for one binary observation per shared question,
  retaining clustered t when questions are grouped and paired t for continuous or repeated
  scores. Holm uses the selected tests as one family. This avoids treating two binary wins
  as p=0 merely because paired differences have zero variance. Output names the method;
  JSON adds `test`, `p_value_used`, and `mcnemar`, while `p_value` retains its paired-t meaning.
  [Controlled example and audit of 173 public submissions](docs/leaderboard-tests.md).

- **Clustered intervals and tests use the bias-reduced CR2 estimator with Satterthwaite
  degrees of freedom** in place of CR1 on t(G − 1). With clusters of equal size the numbers
  are unchanged. With unequal sizes the old test rejected a true null too often: 9.7% to 16.6%
  for a nominal 5% test on SWE-bench Verified's repository sizes, against 3.0% to 5.2% now.
  Clustered intervals on unequal clusters are wider than before, and `leaderboard` groups
  built from them are larger.

### Fixed

- Inspect imports now refuse cancelled/failed runs, incomplete sample counts,
  invalidations, invalid epoch coverage and changing automatic scorer selection.
  Completed limits and selected-ID runs remain supported. Recorded text inputs,
  choices and targets receive content signatures: reused IDs with changed
  questions no longer produce paired inference. Solver-prompt experiments remain
  comparable; rewriting dataset input itself now requires an independently
  reviewed identity mapping. Multimodal/external inputs remain explicitly
  unchecked. [Retained captures and before/after replay](examples/inspect-comparison/README.md).
- A binary score near 0 or 1 got a CLT interval that left [0, 1] (2 correct of 500:
  [-0.0015, 0.0095]; 0 of 500: a zero-width interval). `summarize` and `leaderboard` now use
  the Wilson interval whenever there are fewer than 10 successes or failures, not only below
  30 questions.
- `leaderboard` printed every pair and one letter per group: 15,000 lines for 175 models, and
  group labels that ran past `z`. Past 66 pairs the table shows adjacent ranks (`--all-pairs`
  for the rest). The initial rank-span shorthand is superseded by exact sets above.
- `leaderboard` grouped indistinguishable models by enumerating cliques without pivoting.
  A board of 28 near-tied real submissions took 66 seconds and one of 47 did not finish. It
  now pivots: under a second for 47, about ten seconds for 175 models (15,225 pairs).

- Known question-content conflicts now stop paired comparisons and leaderboards even when
  question IDs match. Native lm-eval imports fingerprint the document and target; canonical
  inputs can carry `question_hash`. Matching, partial and unavailable checks remain distinct.
  Prompt arguments and responses do not enter question identity.
- Exact McNemar tails reuse adjacent integer binomial coefficients. Large binary comparisons
  retain the exact result without rebuilding each coefficient independently.

- Summary and leaderboard means now give each question equal weight after averaging its
  repeated generations. Counts and SEs use distinct questions; retained observation counts
  remain available in JSON and repeated-generation tables. Wilson cannot count repeated
  question averages as independent binary trials.
- Constant nonzero paired differences use the p=0 t-test limit instead of p=1, with explicit
  degeneracy warnings. Score units are scaled before SE/correlation calculations to avoid
  tiny continuous scores underflowing to false zero variance. Matrix/nonfinite inputs,
  invalid group lengths, approximate binary grades in McNemar, and a single independent
  cluster are rejected at the relevant statistical entry points.
- Undefined pairing correlation and variance reduction are exported as JSON null and shown
  as unavailable in the CLI, with explanatory warnings. Callers must handle nullable values
  for constant score vectors instead of interpreting the old fabricated zero as a measurement.
- Input parsing rejects duplicate normalized CSV columns, duplicate JSON fields, missing or
  structured identifiers, and conflicting cluster assignments. Combining sources propagates
  known assignments to the same question and refuses to invent groups for unknown questions.
- Inspect imports refuse missing or unsupported scalar grades and unscored samples, which
  previously became zero scores or silently disappeared. lm-eval imports require document
  IDs and reject duplicate score fields, preserving question identity and original grades.
- Percentile bootstrap resampling now batches temporary indices and indexed scores, while
  retaining every resample mean and the same seeded percentile result. Invalid resample
  counts are rejected rather than producing undefined SEs or allocation errors.

- Both power-planning directions now validate finite parameters and exact integer
  counts consistently. Invalid design effects, negative detectable gaps, infinite
  samples, and unrepresentable counts produce validation errors. Small alpha values
  avoid subtraction cancellation, and variance roots avoid premature overflow.
- Browser curves no longer contain decorative scatter that could be mistaken for
  measurements. The minimum question count stays inside the plot, axis labels keep
  their size on phones, and edits do not restart an animation.
- Small-gap plans use a higher precision AS241 inverse-normal approximation; the
  previous approximation could shift very large required counts by hundreds of
  questions relative to Python. Independent SciPy quantiles cover all three
  approximation regions, including extreme tails.
- Shared formula vectors now sample the full parameter grid instead of truncating
  it to one baseline and one question count. Python checks that they remain current;
  independent SciPy quantile checks exercise additional boundary cases.

### Added

- `compare --html PATH`: a self-contained offline comparison report with a complete shared,
  unmatched and conflicting question ledger; per-generation evidence; source records; cluster
  deletion sensitivity; and full JSON / filtered CSV downloads. Searching and filtering do not
  change inference. Reports with insufficient overlap or conflicting identity remain inspectable
  while the CLI exits with an inference error.
- Score provenance from CSV physical line ranges, JSONL/lm-eval lines, and Inspect sample records.
  HTML uses basenames and source numbers, retains original numeric data in JSON, and contains no
  raw prompts/completions. Script/style hashes and a restrictive CSP keep it offline.

- Fixed-budget planning, precise numeric editors, reset and recovery, a computed
  budget table, and a comparison with zero pairing correlation.
- JSON planning artifacts with explicit assumptions, units and warnings, plus a
  reproducible Python CLI command. Invalid drafts cannot export a stale result.
- Mobile result navigation, small-sample/group caveats, and explicit warnings when
  a mathematical detectable gap exceeds the available accuracy improvement.
- Production Chromium and Firefox workflows covering editing, keyboard use,
  downloads, accessibility, responsive charts, offline use, and blocked storage.

### Maintenance

- Browser lint tooling now uses supported ESLint 10 with its compatible TypeScript plugin.
  Fresh Node 24 checks pass and all production files match the browser-tested build.

- The uv lock now resolves stable Pydantic 2.13.5 and wrapt 2.5.0 instead of
  beta/release-candidate versions selected by a permissive local resolver setting.
  The project explicitly prefers stable releases. The narrow-terminal regression now
  supplies its own terminal environment so it also runs in noninteractive shells.

## [0.2.4] - 2026-10-03

### Security

- A model name or question id holding a terminal escape sequence was printed as it came: the
  tables and the errors that list models sent it to the terminal, which obeys it (clears the
  screen, retitles the window, hides the rest of the line). Each control character in text
  from the data is now written as a visible escape: `m\x1b]0;title\x07`. `--json` already
  escaped them.

## [0.2.3] - 2026-10-03

### Compatibility

- Python 3.13 and 3.14 are tested and declared. CI runs the suite on 3.14
  as well, and the package's classifiers list both versions. The code is
  unchanged: with the newest release of every dependency, the tests pass on
  3.14 and on 3.15's release candidate.

The rest of this release is in the web demo; the package is otherwise
unchanged.

### Changed

- The page's fonts are served by the page itself. They came from Google Fonts,
  the one request the page made to another origin; the same font files (every
  subset, as Google serves them to a current browser) are now in
  `web/src/fonts/`, with their SIL Open Font License texts. Nothing looks
  different: screenshots before and after match. The page now loads with
  every other host blocked.

### Security

- The built page carries a Content-Security-Policy. Scripts, styles, fonts and
  workers load from the page's own origin only, and `connect-src 'self'` has
  the browser refuse to send what you give the page to any other host, even
  for a script injected through a bug in how the page renders a file. Inline
  event handlers and `eval` are not allowed. Every control was exercised
  in Chromium and Firefox with a listener for policy violations: none.

## [0.2.2] - 2026-10-02

Files and pipes as Windows and spreadsheets make them.

### Fixed

- A CSV saved from a spreadsheet. Excel's "CSV UTF-8" starts with a byte-order
  mark, which became part of the first column's name: "missing required column
  'question_id' in row 1" for a file that has it. A spreadsheet in a locale
  whose decimal mark is the comma writes semicolons between the fields and
  `0,75` for a score, which failed the same way. The mark is skipped, the
  delimiter (comma, semicolon or tab) is the one that splits the header into
  the required columns, and decimal commas are read when the delimiter is not
  the comma.
- That error now lists the columns the file does have.
- Output written to a pipe or a file is UTF-8. Before 3.15, Python on Windows
  gives a redirected stdout the system's code page, so
  `errorbars leaderboard scores.csv > table.txt` with a model name outside it
  stopped with "'charmap' codec can't encode characters". (Reproduced on Linux
  by giving the pipe cp1252 with `PYTHONIOENCODING`; the test does the same.)

## [0.2.1] - 2026-10-02

What the table commands print, checked the way their output is read: after `pip install
errorbars`, in a CI log, and with the model names harnesses produce.

### Fixed

- `pip install errorbars` gives a working command line. `rich` is an extra, and without it
  `summarize`, `compare`, `leaderboard` and `power` stopped with "rich is required for table
  output". They print the same rows as aligned plain text now; `errorbars[cli]` still gives the
  `rich` tables.
- Model names are printed whole. Written to a pipe (a CI log, a file), tables were laid out 80
  columns wide and every cell cut to fit: lm-eval's `meta-llama__Llama-3.1-8B-Instruct` and
  `meta-llama__Llama-3.1-70B-Instruct` were both `meta-llam…` in the pairwise table, and the
  column headings were cut too. A pipe gets the table at its full width; a terminal too narrow
  for it folds the names onto more lines and keeps the numbers on one.
- Model names are printed as they are. `rich` read `[q4_k_m]` in a name as style markup and
  dropped it, and a name holding something like `[/b]` ended the command with a `MarkupError`
  traceback. Nothing from the data is parsed as markup or as an emoji code any more.
- The message for a missing `inspect-ai` names the extra (`pip install "errorbars[inspect]"`),
  which also carries the pins inspect-ai needs to import.
- The strict type check passes on Python 3.10 (an array annotation was only complete on the
  numpy releases that need 3.11), and the test for importing an Inspect log is skipped without
  inspect-ai, like the rest.

## [0.2.0] - 2026-10-01

A harness writes one log per model, and every command took exactly one file. Asking whether
model B beats model A, starting from real lm-eval output, was two `import` runs, a
hand-made concatenation of two CSVs, and then `compare`.

### Added

- `summarize`, `compare` and `leaderboard` take one or more files or directories and read
  each as what it is: errorbars' CSV/JSONL, an lm-evaluation-harness `samples_*.jsonl`, or
  an Inspect AI `.eval` log. `errorbars compare out/model-a out/model-b` is the whole
  comparison; `errorbars leaderboard out` ranks every model under an lm-eval output
  directory. Checked against the output directory of two real lm-eval 0.4.13 runs
  (`--model hf`, two tiny models, COPA), committed as a fixture: the means are the
  accuracies lm-eval reported.
- The model of an lm-eval samples file is read from the `results_<timestamp>.json` lm-eval
  writes beside it (`model_name`), so `--model` is no longer required. A samples file moved
  away from its results file has to be named, as `NAME=PATH`; the same form tells two runs of
  one model apart (`greedy=a.eval sampled=b.eval`).
- A directory with several runs of one task (lm-eval adds a timestamped file on every
  re-run) uses the latest and says so on stderr.
- The same model, question and sample in two inputs is refused and both files are named.
- `compare` with exactly two models in the input needs no `--model-a`/`--model-b`. Its
  output says how many questions only one of the two models answered (`n_only_a`,
  `n_only_b` in `--json`), and `leaderboard` says when the models were not scored on the same
  questions.
- `import` takes several logs and directories and writes one CSV. `--metric`, `--filter`
  and `--scorer` are available on every command that reads logs.
- Python: `errorbars.load_inputs`, `errorbars.io.concat`,
  `errorbars.adapters.lm_eval.infer_model_name`.

### Fixed

- `summarize` on a file without a `cluster_id` column printed clustering diagnostics anyway,
  with every question as its own cluster: for 4 questions, "n clusters 4" and a "clustered
  CI" of [-0.05, 1.55]. Diagnostics now need a cluster that groups questions.
- `summarize` without `--model` on a file with several models pooled them: the example
  benchmark's 4 models x 200 questions were summarized as one sample of n = 800 (SE 0.017,
  where each model's is 0.033 to 0.035). It now asks which model, or points to `leaderboard`.
  With one model in the data, the summary is titled with its name instead of `(all)`.

## [0.1.3] - 2026-10-01

### Fixed

- `import lm-eval` on a task with several filters counted every question once
  per filter. `gsm8k_cot_self_consistency` scores each question under
  `score-first`, `maj@8` and `maj@64`, so 4 questions were imported as 12 and
  every standard error shrank accordingly. The adapter now asks which filter to
  use (`--filter maj@8`, or `filter_name=` in Python) and refuses a second
  record for the same `doc_id`. Checked against a real three-filter log from
  lm-eval 0.4.13, committed as a fixture.
- `import inspect` read a scorer that returns several named values as a score
  of 0 for every sample (that is what Inspect's own conversion does with a
  dict). It is an error now. A score that isn't a finite number is rejected by
  both adapters, as it already was when loading a CSV.
- A missing or unreadable file printed a Python traceback. It is one line:
  `error: results.csv: No such file or directory`. A file Inspect can't parse
  is named, and so is a JSONL line that isn't an object (it was a
  `TypeError`).
- A CSV row with too few cells produced a model named `None`; one with too
  many (an unquoted comma in a value) was read with its cells shifted. Both
  are rejected with their row number.
- `leaderboard --alpha` and `summarize --ci bootstrap --confidence` accepted
  any number, including `nan` and values outside 0 to 1. `power --n` accepted
  a correlation outside -1 to 1 (reported as "math domain error") and a design
  effect below 1, which `power --delta` already refused. Infinite or `nan`
  arguments are refused throughout.
- Scores too large to square (beyond 1e100) overflowed into `inf` and `nan`
  results, or an `OverflowError`. They are rejected when loading.

### Added

- `leaderboard --json` reports `p_value_clustered` for each pair. With
  clustered questions the Holm correction is applied to that p-value, and the
  output only showed the unclustered one, so `p_holm` could not be checked
  against it.
- A seeded fuzz test runs 1,200 generated datasets and argument sets through
  the command line: each ends in a result that satisfies the basic invariants
  (intervals in order, p-values in 0 to 1, strict JSON) or in a one-line
  error.

## [0.1.2] - 2026-10-01

### Added

- Published to PyPI: `pip install "errorbars[cli]"`. The README's images and
  links are rewritten to absolute URLs at build time so they work on the
  project page.
- `errorbars --version`.
- `py.typed`, so type checkers use the package's annotations (the `Typing ::
  Typed` classifier was already declared).

## [0.1.1] - 2026-09-30

### Fixed

- The paired test's p-value and CI used the normal distribution, and the
  README called that "somewhat conservative" for small n; it is the opposite
  (at 8 degrees of freedom, a statistic of 2.2 gave p = 0.028 instead of
  0.059). Paired comparisons now use Student's t with n - 1 degrees of freedom
  and match `scipy.stats.ttest_rel` to 1e-7, and clustered SEs (the clustered
  CI in `summarize`, the clustered paired CI and p-value, and so the
  leaderboard's Holm-corrected tests) use t with G - 1 degrees of freedom for
  G clusters. No scipy at runtime: the t tail comes from a continued-fraction
  incomplete beta function. On the bundled example the headline pair's paired
  p moves from 0.1116 to 0.1131, its clustered p from 0.1154 to 0.1235, and
  its Holm-adjusted p from 0.298 to 0.322; groups are unchanged.
  With a single cluster, where the clustered SE falls back to the plain one,
  the clustered test keeps the n - 1 reference too.

- A non-finite score (`nan`, `inf`) was accepted and propagated into every
  mean, CI and p-value; on a leaderboard the NaN model sorted to rank 1.
  Loading now fails with the row number.
- A repeated (model, question, sample) row was counted as another question,
  inflating n and shrinking standard errors. Loading now fails with both row
  numbers and says to give repeated generations distinct `sample` values.
- `power` answered "2 questions" for a baseline of 0 or 1 (where p(1-p) = 0)
  and accepted targets above 100% (`--baseline 0.98 --delta 0.05`). The
  baseline must be strictly between 0 and 1, baseline + delta can't exceed
  1, and a continuous-metric variance must be positive; the web calculator's
  effect-size slider is capped at 1 - baseline to match.
- `compare`/`summarize` with an unknown model name said "fewer than 2 shared
  question_ids" or "no rows"; they now name the missing model and list the
  models in the file.
- Install hints for the optional extras named `errorbars` on PyPI, where it
  isn't published; they now name the dependency or the Git URL.

## [0.1.0] - 2026-09-24

Initial release.

- `summarize`: CLT, Wilson, and bootstrap confidence intervals; clustered
  standard errors with design effect and ICC; within/between-question
  variance decomposition for repeated samples.
- `compare`: paired mean difference, SE, CI, p-value; correlation and
  variance reduction from pairing; clustered paired SE; exact McNemar test
  for binary scores.
- `leaderboard`: per-model CIs, Holm-corrected pairwise paired tests,
  maximal-clique grouping of statistically indistinguishable models, SVG and
  (optional) matplotlib forest plots.
- `power`: questions needed for a target effect/power, and minimum
  detectable effect for a given n, accounting for pairing correlation,
  repeated sampling, and cluster design effect.
- CLI (`errorbars summarize|compare|leaderboard|power|import`) with `rich`
  tables and `--json` output.
- Adapters: `errorbars import lm-eval|inspect` converts
  lm-evaluation-harness `--log_samples` JSONL or an Inspect AI `.eval` log
  into the canonical format, verified against real output from lm-eval
  0.4.13 and inspect-ai 0.3.268.
- Web calculator (Vite + TypeScript) mirroring the Python power formulas,
  with shared JSON test vectors.
