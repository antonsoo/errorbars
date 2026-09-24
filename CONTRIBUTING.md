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
npm install
npm run dev      # local dev server
npm test         # vitest, checks against Python-generated test vectors
npm run build
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
