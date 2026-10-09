# Inspect import verification, 2026-10-09

Implementation: `b19d721`. Before snapshot: `20437eb`. All changes are local;
no package publication, push or site deployment was performed.

## What changed, and why

Inspect logs carry original dataset input separately from solver messages, and
planned/completed sample counts separately from the retained score records.
The importer previously ignored that information. The controlled recordings in
[the walkthrough](../examples/inspect-comparison/README.md) showed two consequences:
different questions sharing IDs produced a paired p-value of 6.44449e-7, and
incomplete or cancelled logs became apparently usable score tables.

The importer now validates complete successful cohorts and computes exact
content signatures for supported text samples. Conflicts withhold inference
while retaining the observations in the HTML ledger. Completed selection limits,
repeated epochs, and solver prompt variants remain usable. Automatic scorer
selection must stay consistent within a log.

## Recorded workflow evidence

Five fresh runs were captured through the real `mockllm/model` provider in
Inspect AI 0.3.268, using synthetic arithmetic and scripted responses. Their
unedited `.eval` files and byte digests are committed. Fresh runs through Inspect
0.3.277, installed independently on Python 3.14, produced the same identity and
cohort outcomes. These are software integration experiments, not a model study.

The [before](../examples/inspect-comparison/evidence/before-20437eb.json) and
[after](../examples/inspect-comparison/evidence/after.json) files retain full
cohort counts and comparisons. The before run imported source from a `git archive`
of `20437eb`; the after run used an installed wheel outside the source checkout.

The installed CLI was also invoked through `python -I -m errorbars.cli compare`:

| Inputs | Exit | JSON stdout | HTML |
| --- | ---: | --- | --- |
| Original and solver variant | 0 | 24 matching, mean difference 2/3 | Complete report |
| Original and different questions | 1 | Empty; error names 24 conflicts | Observations retained, inference unavailable |

The valid comparison's p-value is independently checked against
`scipy.stats.ttest_rel`, reading the score codes directly from the original logs.
Changes to input, target or choices independently block pairing. Content markers
inserted in private-source tests do not appear in JSON or HTML exports. CSV
conversion preserves the signatures and therefore preserves conflict detection.

## Checks run

| Check | Result |
| --- | --- |
| Fresh Python 3.12 environment, locked dev dependencies, full `pytest -q` | 483 passed |
| `uv run --locked ruff check .` | Passed |
| `uv run --locked mypy src/errorbars` | Passed |
| `uv build` | Wheel and source distribution built |
| Installed wheel, Python 3.10.21, NumPy 1.24.0, Inspect 0.3.268; adapter/identity tests | 71 passed |
| Base wheel before installing Inspect extra | `power --delta 0.03 --baseline 0.5` returned 4361 |
| Installed wheel, Python 3.14.7, Inspect 0.3.277 | Retained replay and fresh captures checked |
| Web clean install, lint, typecheck, unit tests, production build | Passed; 680 unit tests |
| Production site browser workflows | 40 passed |
| Existing offline report workflows using installed wheel | 22 passed |
| New Inspect report workflows, both engines at 1440px and 375px | 12 passed |
| Retained log SHA-256 digests and archive contents | All five match; no workspace or temporary paths |
| `git diff --check` | Passed |

Commands from the repository root (use a fresh temporary directory for the
environments). The `--python` arguments below are interpreter/venv selections,
not publication steps:

```sh
audit_dir="$(mktemp -d)"
UV_PROJECT_ENVIRONMENT="$audit_dir/dev" uv sync --locked --group dev --extra all --python 3.12
UV_PROJECT_ENVIRONMENT="$audit_dir/dev" uv run --locked pytest -q
UV_PROJECT_ENVIRONMENT="$audit_dir/dev" uv run --locked ruff check .
UV_PROJECT_ENVIRONMENT="$audit_dir/dev" uv run --locked mypy src/errorbars
uv build

uv venv --python 3.14 "$audit_dir/installed"
uv pip install --python "$audit_dir/installed/bin/python" 'dist/errorbars-0.2.4-py3-none-any.whl[inspect]'
"$audit_dir/installed/bin/python" -I examples/inspect-comparison/replay.py "$audit_dir/reports"

uv venv --python 3.10 "$audit_dir/minimum"
uv pip install --python "$audit_dir/minimum/bin/python" 'dist/errorbars-0.2.4-py3-none-any.whl[inspect]' 'numpy==1.24.0' 'inspect-ai==0.3.268' 'pytest>=9.0.3' 'scipy>=1.11'
"$audit_dir/minimum/bin/python" -m pytest -q tests/test_inspect_integrity.py tests/test_adapters.py tests/test_question_identity.py

npm --prefix web ci
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
npm --prefix web run test:browser
ERRORBARS_REPORT_PYTHON="$audit_dir/installed/bin/python" npm --prefix web run test:reports
node examples/inspect-comparison/check-reports.mjs "$audit_dir/reports"
```

The website build produces `web/dist/`. The report browser checks use `file://`
with networking disabled, exercise keyboard inspection and download the complete
JSON. They verify scores, IDs, conflict states and repeated observations from the
downloads, and check for page errors and horizontal overflow. No new UI was
introduced; the existing report's unavailable state now receives Inspect conflicts.

Screenshots inspected visually:

- [Desktop](assets/inspect-conflict-1440.png): withheld estimate and all 24 conflicts
  are legible in the existing two-column report.
- [Phone](assets/inspect-conflict-375.png): controls and explanation wrap within
  the viewport; the ledger remains below the fold.

## Import cost

`benchmark.py` expands the retained original into a **synthetic** 1,000-record,
1,835,141-byte Inspect log. It updates the selected IDs and cohort counts, then
measures five complete imports, excluding file generation and the initial SDK
import. It does not measure report rendering or model execution.

On this 14-vCPU WSL2 Linux machine, Python 3.12 with Inspect 0.3.268:

| Version | Median | Observed range | Known signatures |
| --- | ---: | ---: | ---: |
| `20437eb` | 1162 ms | 1070-1199 ms | 0 |
| Changed importer | 1090 ms | 1060-1193 ms | 1000 |

The ranges overlap; this does not establish a speed improvement. Timing varies
with local load and caches. Raw observations are retained in
[timing-before.json](../examples/inspect-comparison/evidence/timing-before.json)
and [timing-after.json](../examples/inspect-comparison/evidence/timing-after.json).

```sh
mkdir -p "$audit_dir/before"
git archive 20437eb src | tar -x -C "$audit_dir/before"
PYTHONPATH="$audit_dir/before/src" uv run python examples/inspect-comparison/replay.py "$audit_dir/before-reports"
PYTHONPATH="$audit_dir/before/src" uv run python examples/inspect-comparison/benchmark.py "$audit_dir/timing-before"
uv run python examples/inspect-comparison/benchmark.py "$audit_dir/timing-after"
```

## Remaining limits

- This is an exact text-definition check, not semantic question matching. Native
  Inspect experiments that rewrite dataset input itself now conservatively
  conflict; a separately reviewed canonical identity mapping is needed.
- Media, tool histories, sandbox/file/setup inputs, missing targets and unresolved
  text attachments remain unchecked. Missing identity evidence is reported but
  does not prohibit ID-based inference.
- Matching text signatures do not verify scorer equivalence, metadata, external
  state or benchmark representativeness. A complete log can still be a biased
  selection, and consistent edits to records plus headers cannot be authenticated.
- Incomplete/early-stopped native logs are refused. There is no selection-aware
  estimator or implicit import of only the successfully scored subset.

Suggested repository description (unchanged scope):
"Error bars for LLM evals, with paired comparisons and inspectable question-level evidence."
Suggested topics: `llm-evaluation`, `statistics`, `confidence-intervals`,
`inspect-ai`, `benchmarking`, `python`.
