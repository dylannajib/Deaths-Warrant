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

* **Inputs** say how to read a value from the record (`extract`):
  * age and sex;
  * the latest LOINC observation, with unit conversion;
  * a coded observation;
  * diagnoses: diagnosis category, condition present, weighted condition sum (e.g. Charlson);
  * years since a diagnosis, or since the diagnosis in the matched category;
  * medication present;
  * `first_of`, a list of rules tried in priority order.

  How the `missing` field works:
  * no `missing` (`null`): the input is required;
  * a distribution: the input is averaged over that distribution when absent;
  * `[]`: the input is optional, and only layers that `require` it may use it.
* **Layers** are tried in order, and the first whose `requires` inputs are all present is used.
  The last layer must require nothing. Survival forms:
  * `weibull_ph`;
  * `life_table_ph`: population mortality × a hazard ratio;
  * `relative_survival`: population mortality × published relative survival, conditional on
    the years since diagnosis.

  Terms can be `linear`, `bands` or `category`. A new form needs the same change in
  `evaluate.py` and `src/frontend/src/engine/evaluate.ts`.
* **Sources**: every coefficient must trace to a published, citable source with a licence that
  permits redistribution of derived coefficients. Record them in `sources` and `sources.md`.
* **Source data**: write a builder in `src/backend/deaths_warrant/sources/` that downloads the
  published table into the git-ignored `data/` cache and writes a small JSON file into your
  model folder. Commit the JSON so the export is reproducible offline. Builders exist for NCHS
  life tables, SEER*Explorer and SNOMED CT hierarchies (`snomed_roots.json` →
  `snomed_sets.json`, because the browser matches SNOMED codes exactly).
* **Validation**: put a `validate.py` in your folder that reads real, published patient data
  from `data/` and writes `validation.json`. `build()` loads that file into the spec. Report
  only aggregate results (`n >= 20`), never commit patient-level data, and never train on
  data you then validate on. `src/models/cancer/validate.py` is a worked example.

The unit-test fixture in `src/models/_fixture/model.py` is a compact example of every survival
form; `src/models/cancer/` is a complete real model.

## 2. Export and test

```bash
cd src/backend
../../.venv/bin/python -m deaths_warrant.export   # writes spec.json + golden.json
../../.venv/bin/python -m pytest
cd ../frontend && npm test                        # replays golden.json in TypeScript
```

Commit `model.py`, `spec.json`, `golden.json`, `sources.md` and any source-data JSON,
`validate.py` and `validation.json`. CI fails if the exported files
are stale or if the TypeScript evaluator disagrees with Python. The model appears in the site's
disease-group picker automatically.
