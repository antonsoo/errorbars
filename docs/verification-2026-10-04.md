# Evaluation planner verification - 2026-10-04

The planner and numeric changes in `3c7611a`, `19101c1`, and `e063acf` were
verified from a separate clean checkout. Changes remain local; no package
publication, source push, or site deployment was performed for this update.

## Completed work

| Local Beads ticket | Result |
| --- | --- |
| `officina-3ez` | Consistent finite-domain and integer-count validation in forward and inverse planning |
| `officina-57q` | Fixed-budget planning, exact editors, reset/recovery, sensitivity, JSON artifacts and CLI reproduction |
| `officina-tri` | Computed charts, responsive labels, numeric alternatives, mobile navigation and production browser checks |
| `officina-ayp` | Higher precision AS241 quantiles and small-effect comparisons with independent oracles |

## Reproductions that drove the changes

- Python accepted `n_questions=2.5` and infinite repeated samples. The latter
  returned two questions and zero variance. Both are now validation errors.
- At power `0.001`, the previous inverse formula returned a negative detectable
  effect. Both directions now reject a nonpositive normal-quantile sum.
- `delta=1e-200` caused a division-by-zero exception. Unrepresentable plans now
  produce an actionable validation error, including through the CLI.
- The browser accepted `NaN` delta, infinite variance, invalid correlation,
  and design effects below one in cases Python rejected. The paths now share
  the same numeric contract.
- The old chart's x-axis started at eight questions when a valid plan could
  require two; its marker could fall outside the plot. It also drew decorative
  scatter without identifying it as synthetic and shrank labels on phones.
- Truncating a Cartesian product had confined all 400 forward vectors to one
  baseline and all 200 inverse vectors to one question count. The new vectors
  sample the whole grid, including six baselines and seven question counts.
- Adding the browser's smallest gap to the oracle grid exposed 46 forward-count
  failures in the previous inverse-normal approximation. For baseline `0.9`,
  gap `0.0001`, alpha `0.001`, power `0.8`, rho `0`, two samples, and design
  effect `1000`, Python returned **153,671,821,247**, while JavaScript returned
  **153,671,820,944**. The AS241 implementation passes all expanded count
  comparisons exactly. Its provenance and upstream license are retained and
  bundled with the site.

## Checks and environments

| Check | Result |
| --- | --- |
| Clean Python 3.14.7, locked dev and all extras | 293 tests passed |
| Python 3.10.21, oldest declared direct dependencies | 293 tests passed; final expanded power vectors also passed (49 focused tests) |
| Python lint and strict types | Ruff and mypy passed |
| Clean Node 24.21.0 / npm 11.19.0 install | `npm ci` passed |
| TypeScript suite | 650 tests passed |
| Production Chromium and Firefox suite | 26 workflows passed |
| Accessibility | 16 Axe scans; zero violations |
| Python source distribution and wheel | Built successfully |
| Production site | Built successfully; all 56 files match the Node 26.7.0 working build byte for byte |
| License artifact | Bundled PSF license matches the retained source license byte for byte |
| Bare wheel consumer on Python 3.10 | Installed with only required runtime dependencies; both CLI planning modes passed |

The oldest-dependency suite produced one Matplotlib/Pyparsing deprecation
warning. It had no test failures. Tests ran on WSL2 Linux.

Commands used from the clean checkout:

```bash
uv sync --locked --python 3.14 --group dev --extra all
uv run --no-sync ruff check .
uv run --no-sync mypy src/errorbars
uv run --no-sync pytest -q
uv build
npm ci --prefix web
npm run lint --prefix web
npm run typecheck --prefix web
npm test --prefix web
npm run build --prefix web
npm run test:browser --prefix web
```

The minimum-dependency environment used Python 3.10 and
`uv pip install --resolution lowest-direct -e '.[all,inspect]' --group dev`.
The final source change after that full run affected browser quantiles and
shared oracle vectors; the updated power suite was rerun in that environment.

## Independent and end-to-end evidence

The 400 forward counts and 200 inverse outputs are checked against current
Python `NormalDist` calculations, and Python checks that the committed vectors
remain current. The browser's 24 additional quantile vectors come from SciPy
`ndtri`, covering central and both tail regions, including probabilities
`5e-324` and `1 - 2**-53`. Python power checks use independent SciPy quantiles
and the existing paired-score simulation tests.

Browser workflows exercise exact edits, slider keyboard use, switching modes
with an invalid inactive draft, blocked downloads during errors, impossible
improvements, small groups, reset and focus retention, the two-question
marker, extreme valid plans, resize, offline use, blocked storage, and JSON
downloads. The tested sessions had no page exceptions, CSP violations, or
off-origin requests. The extreme browser case also matches Python's exact
**3,969,623,374,926** question count.

A real downloaded plan with baseline `65.4321%`, gap `3` points, rho `0.3`,
average cluster size `3.5`, ICC `0.2`, alpha `5%`, and power `80%` reproduced
**4,143 questions** through its generated Python CLI command. JSON retains
full precision even when the visual presentation rounds a number.

README CLI examples were exercised against the committed synthetic data and
harness fixtures. Placeholder harness paths were substituted with fixture
paths; Inspect syntax checks used named copies of the same shared-question
fixture. Initial use of two unrelated Inspect fixtures was correctly rejected
because they had no shared question IDs. The bare-wheel quickstart returned
**4,361 questions** and its 500-question inverse returned approximately
**8.859 percentage points**.

## Visual review

Real production screenshots were opened and inspected in light and dark
styles at desktop and phone widths. The chart's numeric labels remain readable
at 375 pixels, the budget table fits, and the fixed mobile link reaches either
the complete plan or an invalid field.

- [Desktop, questions mode](assets/planner-light-1440.png)
- [Desktop, budget mode](assets/planner-dark-1440.png)
- [Phone, questions mode](assets/planner-light-375.png)
- [Phone, budget mode](assets/planner-dark-375.png)
- [README hero](assets/calculator-hero.png)

## Limits and release scope

The normal-approximation model remains a planning tool; it is not an exact
binary paired power calculation or an estimate of correlation from observations.
Small-sample/group warnings do not establish a sharp statistical validity
threshold. Bernoulli feasibility, unequal cluster sizes, and multiplicity need
separate consideration. The JSON format has no import workflow, and plans are
not persisted between visits. See [planning.md](planning.md) for these limits.

Browser verification covered Chromium and Firefox, not Safari or mobile device
hardware. The build command is `npm run build --prefix web`; deployment input
would be `web/dist/`. Hosted behavior was not checked because this update was
not deployed.
