# Contributing a prognosis model

Each disease group lives in `src/models/<id>/` (lower-case id, letters, digits, `_`).

## 1. Write `model.py`

It must define two functions:

```python
from deaths_warrant.spec import ModelSpec

def build() -> ModelSpec:
    """Return the complete spec: inputs, layers, coefficients, sources."""

def golden_inputs() -> list[dict]:
    """Observed-input sets that together exercise every layer."""
```

`src/backend/deaths_warrant/spec.py` documents every building block:

* **Inputs** say how to read a value from the record (`extract`): age, sex, latest LOINC
  observation (with unit conversion), coded observation, diagnosis category, condition present,
  weighted condition sum (e.g. Charlson), years since diagnosis, medication present. An input
  with a `missing` distribution is optional; without one it is required.
* **Layers** are tried in order; the first whose `requires` inputs are all present is used.
  The last layer must require nothing. Survival forms: `weibull_ph` and `life_table_ph`, with
  `linear`, `bands` and `category` terms. New forms need the same change in
  `evaluate.py` and `src/frontend/src/engine/evaluate.ts`.
* **Sources**: every coefficient must trace to a published, citable source with a licence that
  permits redistribution of derived coefficients. Record them in `sources` and `sources.md`.
* **Validation**: report only aggregate results (`n >= 20`) from real published patient data.
  Never commit patient-level data, and never train on data you then validate on.

The unit-test fixture in `src/models/_fixture/model.py` is a compact example of a full spec.

## 2. Export and test

```bash
cd src/backend
../../.venv/bin/python -m deaths_warrant.export   # writes spec.json + golden.json
../../.venv/bin/python -m pytest
cd ../frontend && npm test                        # replays golden.json in TypeScript
```

Commit `model.py`, `spec.json`, `golden.json` and `sources.md`. CI fails if the exported files
are stale or if the TypeScript evaluator disagrees with Python. The model appears in the site's
disease-group picker automatically.
