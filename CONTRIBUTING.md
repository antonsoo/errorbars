# Contributing

## Python package

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[all]" --group dev
pytest
ruff check .
mypy src/errorbars
```

Regenerate the synthetic example data with `python examples/generate_synthetic.py`.

## Web calculator

```bash
cd web
npm ci
npm run dev      # local dev server
npm test         # vitest, checks against Python-generated test vectors
npm run build
npx playwright install chromium firefox  # first setup only
npm run test:browser  # production build, both browser engines
```

If you change a formula in `src/errorbars/power.py`, regenerate the shared
test vectors (`python scripts/export_test_vectors.py`) so the TypeScript
implementation is checked against the same numbers.

## Standalone comparison reports

The Python package renders reports from `src/errorbars/report_assets/`. It embeds
the local fonts and their licenses, JSON evidence and a dependency-free script.
Editing a template or script requires no frontend build. Keep imported labels as
text, the CSP hashes exact, and the evidence download complete when views are paged.

```sh
uv sync --locked --group dev --extra all
npm ci --prefix web
npm run test:reports --prefix web
```

This generates real-capture and synthetic reports, then opens the actual files
offline in Chromium and Firefox. It uses the root `.venv` by default. To check an
installed wheel, set `ERRORBARS_REPORT_PYTHON` to that environment's Python executable.
The CI workflow installs a built wheel with NumPy only before these browser checks.

## Guidelines

- Keep the core statistics dependency-free (numpy only); scipy/statsmodels
  are test-time oracles, never runtime imports.
- Any new statistic needs a test against an independent oracle (a reference
  library, closed form, or Monte Carlo simulation) — see `tests/`.
- Run `ruff check .`, `mypy src/errorbars`, and `pytest` before opening a PR.

## Community and private reports

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Anton Soloviev
maintains this project and handles conduct reports at
[anton@praviel.com](mailto:anton@praviel.com).

Use the bug or improvement forms for public issues. For a suspected security
vulnerability or a conduct concern, email the maintainer privately with the
repository name and relevant details. Do not post credentials, personal data,
private logs, or confidential documents in a public issue.
