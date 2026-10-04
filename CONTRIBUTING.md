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
