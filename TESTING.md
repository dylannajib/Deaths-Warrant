# Testing

## Run everything

```bash
cd src/backend && ../../.venv/bin/ruff check . ../prognosis-models && ../../.venv/bin/python -m pytest && ../../.venv/bin/python -m general.export --check
```

```bash
cd src/frontend && npm test && npm run build
```

CI runs both on every push. Tests that need real patient data are skipped when the data is
absent. Each `validate.py` says how to download its data into the git-ignored `data/`.

## What the suites check

| Suite | Checks |
|---|---|
| Python (`src/backend/tests/`) | Bad specs are rejected. The evaluator matches hand-worked results for every survival form. The life table, MAGGIC, ADO and SEER reproduce their published figures. Exports are up to date. |
| Golden parity | The browser evaluator matches Python on every golden case to 1e-9. |
| Parsers | FHIR JSON, FHIR XML, C-CDA, dates, and five official HL7 examples. |
| Hostile input | XXE, entity expansion, 100,000-level nesting, `__proto__` keys, binary and HTML files, and 2,800 fuzzed HL7 files. All are rejected or read safely, none crash. |
| Result view | Text from the file is shown as text, never as HTML. |
| MIMIC-IV FHIR demo | All 100 real patients run through every model: no crashes, sane curves, disease-group detection agrees with an ICD check for all 300 runs, slowest run 127 ms, a 58 MB file in 0.7 s. |

## Accuracy on real patients

No model was built from any of these datasets. Patient-level data has outcomes from 2010
onwards. Published cohorts are used if their follow-up runs past 2010.

* **Ranking (C-index):** share of patient pairs put in the right order. 50% is a coin flip.
* **Calibration:** predicted against observed percentage alive.

| Model | Data (period) | Ranking | Predicted vs observed alive |
|---|---|---|---|
| Cancer | MSK-CHORD, 24,067 patients (2014 to 2023) | 71% | 1/3/5 y: 71/51/42% vs 80/57/46% |
| Cancer | TCGA, 4,709 patients (diagnosed 2010 to 2013) | 74% | 1/3/5 y: 83/69/62% vs 89/70/61% |
| Heart failure | FAR NHL, 1,088 outpatients (2014 to 2017) | 74% | 2 y: 79.7% vs 85.1% |
| Heart failure | UCI, 299 inpatients (2015) | 72% | 6 months: 89.6% vs 65.4% |
| Heart failure | Brazil MAGGIC validation (2008 to 2014) | | 3-year deaths: 20.9% vs 33.4% |
| Stroke | Australia and New Zealand, 313,162 (2008 to 2017) | | 1/5/10 y: 74.9/51.6/32.9% vs 73.0/52.8/36.4% |
| Stroke | England SSNAP (2013 to 2016) | | 1 y: 72.3% vs 73.6% |
| Respiratory | NHANES, 2,602 patients (2011 to 2019) | 78% | 1/3/5 y: 98.6/95.5/92.1% vs 98.1/95.2/91.7% |
| Respiratory | U.S. pooled cohorts (to 2020) | | Life expectancy vs no COPD, GOLD 1 to 4: 91/79/55/44% vs 93/76/61/50% |

## Known limitations

* U.S. population mortality is used for every patient.
* MAGGIC (1980 to 2006) and ADO (1980s to 2000s) predate current treatments.
* The stroke layer rests on ischaemic strokes in people aged 66 or over.
* Cancer is too pessimistic in the first year, because both test sets only include patients
  fit enough for surgery or sequencing. This is documented, not tuned away.
