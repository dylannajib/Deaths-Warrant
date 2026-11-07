# Adding a prognosis model

A model is one folder, `src/prognosis-models/<id>/` (lower-case letters, digits, `_`). The
site, the exporter and CI find it automatically. No other code changes.

## 1. Write `model.py`

```python
from general.spec import ModelSpec

def build() -> ModelSpec: ...            # inputs, layers, coefficients, sources
def golden_inputs() -> list[dict]: ...   # test inputs that reach every layer
```

`src/backend/general/spec.py` defines every building block. `cancer/` is a full example and
`_fixture/` a small one.

* **Inputs** say how to read a value from the record: age, sex, the latest observation, a
  diagnosis (optionally only from a recent hospital stay), years since a diagnosis, or a
  medication. If an input can be missing, give it a population distribution to average over.
* **Layers** are tried in order and the first whose inputs are present is used. The last layer
  must need nothing. Survival forms: `weibull_ph`, `life_table_ph`, `relative_survival`,
  `score_weibull`, `score_life_table`. A new form must be added to both `evaluate.py` and
  `src/frontend/engine/evaluate.ts`.
* **Sources:** every number must come from a published, citable source whose licence allows
  reuse. List them in the spec and in `sources.md`.
* **Source data:** a script in your folder (like `cancer/build_seer.py`) downloads the
  published table into `data/` and writes a small JSON file next to it. Commit the JSON.

What the existing models rely on:

* **Helpers:** `general.authoring` has `Condition` (a diagnosis with its codes, hazard ratio
  and source), `codes`, `condition_present`, `group_codes`, `hr_term`, `bands`,
  `population_survival`, `load_json` and `NCHS_US_2024`, the citation of the U.S. life table
  loaded with `general.registry.load_life_table("us_2024")`.
* **SNOMED CT:** list root concepts in `snomed_roots.json`, then run
  `python -m general.sources.snomed <id>` from `src/backend` to write the expanded
  `snomed_sets.json`. Read it with `general.authoring.snomed_sets(HERE)`.
* **Citations:** `cardiovascular/` and `respiratory/` keep theirs in `sources.json`, as a
  `"model"` list (coefficient sources) and a `"validation"` list (test data). `build()` adds
  `NCHS_US_2024` after the model list. `cancer/` writes its citations in `model.py`, because
  the SEER citation includes the retrieval date from `seer_relative_survival.json`.
* **Validation results:** `build()` loads them with
  `validation_results(HERE / "validation.json")`, so run `validate.py` before exporting.

## 2. Validate on real patients

Write `validate.py` (see `cardiovascular/validate.py`). It reads real, published patient data
from the git-ignored `data/` and writes `validation.json` with `general.validation`.

* Patient-level outcomes from 2010 onwards, or published cohorts followed past 2010. Label
  each result with its period.
* Never test on data the model was built from.
* Report only groups of 20 or more. Never commit patient-level data.

CI fails if a model has no validation results.

## 3. Export, test, commit

```bash
cd src/backend
../../.venv/bin/python -m general.export   # writes spec.json, golden.json, summary.json
../../.venv/bin/ruff check . ../prognosis-models && ../../.venv/bin/ruff format --check . ../prognosis-models
../../.venv/bin/python -m pytest
cd ../frontend && npm test                 # checks TypeScript matches Python
```

Commit the whole folder. Add a row to the models table in `README.md` and the accuracy table
in `TESTING.md`.

## When something goes wrong

* **Browser:** problems with the uploaded file throw a `RecordError` and its message is shown.
  Anything else is a bug: the page shows a short reference and the full stack goes to the
  console (source maps are on). See `src/frontend/errors.ts`.
* **Export:** errors name the model folder, and for a golden case its index and inputs.
