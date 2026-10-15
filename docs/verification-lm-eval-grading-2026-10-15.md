# Native generation grading verification, 2026-10-15

The [study](../studies/lm-eval-grading/README.md) retains five unedited local
lm-eval 0.4.13 captures. Scripted providers answer constructed questions; this
is a software reproduction, not a benchmark of trained models.

Changing only the built-in `exact_match` grader's `ignore_case` setting changed
24 unchanged answers' grades from 33.3% to 66.7%. The old reader discarded the
setting and reported exact McNemar p = 0.0078125. The corrected reader retains
the grading declaration fingerprint: all 24 questions have matching identity
and conflicting scoring evidence, so inference and ranking are unavailable.
The HTML report still preserves both observed grades and their source records.

A control changes eight answers under the same grader. It retains the valid
-0.3333 difference and p = 0.0078125. Reordering declaration keys and changing
the prompt template also remain usable controls. Custom processors and other
output types retain explicitly unchecked definitions: those paths do not use
the generation metric kwargs being fingerprinted.

## Clean source and installed artifacts

The [receipt](../studies/lm-eval-grading/results/verification.json) identifies
the tested `5bb9312` archive and wheel/sdist hashes. Later evidence edits change
only documentation and the standalone browser reproduction script.

| Workflow | Observed result |
| --- | --- |
| Fresh archive, Python 3.14.7, locked NumPy 2.5.3 | Ruff, mypy on 20 source files, 783 tests, wheel and sdist build pass |
| Minimal wheel, Python 3.10.21 / NumPy 1.24.0 | 28 grading CLI workflows and 17 prior metric workflows pass; all 28 runtime files equal source |
| Minimal wheel, Python 3.14.7 / NumPy 2.5.4 | Same workflows and file comparisons pass |
| Clean Node 24.21.0 install | Lint, typecheck, 691 tests and production build pass |
| Installed-wheel reports in Chromium / Firefox | All 36 report cases pass, including the two new native grading cases |
| Eight fresh offline report contexts, 1440 / 375 pixels | 16 downloads verified; eight screenshots opened and inspected; no page errors or HTTP requests |

The minimal environments contain only errorbars and NumPy. Each runs outside
the source checkout and executes the documented power quickstart, returning
4,361 questions. Native imports and canonical CSV comparisons preserve the
same conflict or common-grader result. Refused ranking preserves an existing
SVG. Twelve generated CSV/HTML artifacts are byte-identical between the source
environment and both minimal wheels.

The web application's 65 built files are byte-identical to the previously
verified build. Its 52 production-page browser checks were not repeated;
the changed report fixtures and actual installed reports were checked afresh.
No frontend or report asset implementation changed in this repair.

Clean source commands:

```bash
uv sync --locked --python 3.14 --group dev --extra all
.venv/bin/ruff check .
.venv/bin/mypy src/errorbars
.venv/bin/pytest -q
uv build
```

Run the [replay](../studies/lm-eval-grading/replay.py) and
[native/canonical workflow verifier](../studies/lm-eval-grading/verify.py)
through the wheel environment's Python, as described in the study. In `web/`,
after `npm ci --no-audit --no-fund`, run `npm run lint`, `npm run typecheck`,
`npm test`, `npm run build`, then `npm run test:reports` with
`ERRORBARS_REPORT_PYTHON` pointing to the separately installed wheel.

## Offline evidence

The [browser runner](../studies/lm-eval-grading/browser.mjs) opens the actual
wheel-generated conflict and common-grader reports after disconnecting each
fresh browser context. Filtered CSV contains one question and preserves its
conflict state and blank unavailable difference. Complete JSON still contains
all 24 questions and both configuration fingerprints. An independent Python
CSV reader checks all eight downloads in the
[download receipt](../studies/lm-eval-grading/results/csv-download-checks.json).

Screenshots retain the existing readable layout, wrapped source names and
distinct matching/conflicting states with no horizontal overflow:

- Chromium: [desktop conflict](assets/lm-eval-grading/chromium-1440-folded.png),
  [phone conflict](assets/lm-eval-grading/chromium-375-folded.png),
  [desktop control](assets/lm-eval-grading/chromium-1440-improved-strict.png),
  [phone control](assets/lm-eval-grading/chromium-375-improved-strict.png).
- Firefox: [desktop conflict](assets/lm-eval-grading/firefox-1440-folded.png),
  [phone conflict](assets/lm-eval-grading/firefox-375-folded.png),
  [desktop control](assets/lm-eval-grading/firefox-1440-improved-strict.png),
  [phone control](assets/lm-eval-grading/firefox-375-improved-strict.png).

Matching recorded parameters do not establish equivalent plugin code,
dependencies, authentication or unrecorded grader state. Explicit and omitted
defaults may conservatively differ. The study documents these boundaries.
The verified source commits were pushed with the owner's authorization. The
[public-source receipt](../studies/lm-eval-grading/results/source-publication.json)
records clean source and GitHub `main` equality at `dd63d96`, plus eight
byte-identical files fetched from immutable public URLs. No PyPI release or
manual deployment was performed.
