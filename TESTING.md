# Testing

This file covers how Death's Warrant is tested and what the tests found. All figures come from
the committed test suites and each model's `validation.json`.

## Running everything

```bash
cd src/backend && ../../.venv/bin/ruff check . ../models && ../../.venv/bin/python -m pytest && ../../.venv/bin/python -m deaths_warrant.export --check
```

```bash
cd src/frontend && npx tsc --noEmit && npm test && npm run build
```

CI runs both on every push. Some tests use real patient data, which is never committed. They
are skipped when the data is absent; each model's `validate.py` and the MIMIC builder explain
how to download it.

## What the suites prove

**Python: 58 tests (`src/backend/tests/`)**

* Every malformed model spec is rejected when it is exported.
* The evaluator matches hand-worked closed-form results for every survival form, including
  mixing over missing inputs, conditional survival and the population cap.
* The NCHS life table reproduces the published life expectancy at 65 and 80 to within
  0.02 years.
* MAGGIC, ADO and SEER reproduce their published tables exactly.
* Exports are deterministic, and CI fails if they are stale.

**TypeScript: 124 tests (`src/frontend/src/`)**

| Area | What is checked |
|---|---|
| Golden parity | The browser evaluator reproduces every Python result for every model to 1e-9. |
| Extraction | Every rule that reads a value from a record. |
| Parsers | FHIR JSON, FHIR XML and C-CDA, and the date rules. |
| Official HL7 examples (CC0) | Three C-CDA documents and two FHIR R4 examples. The XML and JSON forms of the same FHIR resource must give identical records. |
| Hostile input | Malicious and malformed files, plus 2,800 seeded fuzz mutations (details below). |
| Result view | It renders the headline and both dropdowns, and text from the uploaded file is escaped, never treated as HTML. |
| End to end (local data) | The 100 real patients of the MIMIC-IV FHIR demo (details below). |

## End to end on real FHIR: MIMIC-IV FHIR demo

The demo holds 100 de-identified patients (PhysioNet, ODbL). Every patient was run through the
same parse → extract → evaluate pipeline that the browser uses, for all three disease groups:
300 runs in total. Each record was evaluated as of its own newest entry, because MIMIC shifts
its dates into the 2100s.

* **No crashes:** every run finished. The survival curves always fall over time, and the
  range always brackets the median.
* **Diagnosis matching:** the app's check that a record belongs to a group agreed with an
  independent ICD check for 100/100 patients in every group: 22 cancer, 71 cardiovascular,
  27 respiratory.
* **Speed:** the slowest single run took 127 ms. A 58 MB file (real structure, repeated past
  the 50 MB soft limit) took 0.7 s to parse and analyse.
* **What the records held:**
  * Years since diagnosis was found for 21/22 cancer patients and 24/24 heart-failure patients.
  * A cancer stage was found for 8/22 cancer patients (from metastasis codes).
  * Systolic blood pressure was found for 38/71 cardiovascular patients.
  * MIMIC has no echocardiography results and its lab codes are not LOINC, so no ejection
    fraction or creatinine was found. MAGGIC therefore never applied, and those patients used
    the heart-failure-by-age layer, as designed.

This test checks robustness on real records; it is not an accuracy test. Accuracy is below.

## Accuracy on real, published patient data

No model was fitted to any of these datasets.

| Model | Data (outcomes period) | Ranking (C-index) | Calibration |
|---|---|---|---|
| Cancer | MSK-CHORD, 24,067 patients (sequenced from 2014, outcomes to Sep 2023) | 0.71 (0.68 using registry stage only) | 1/3/5-year survival: predicted 0.71/0.51/0.42, observed 0.80/0.57/0.46. For patients who died, the predicted 25–75% range held the actual years lived for 51% of them (50% is ideal). |
| Cardiovascular | UCI heart-failure records, 299 patients (2015) | 0.72 | Overestimates 6-month survival: 0.93 predicted vs 0.65 observed. Every patient was NYHA class III–IV, which their records did not say. |
| Cardiovascular | Published cohorts: acute stroke (2008–17); Brazilian MAGGIC validation (2008–14) | – | Stroke survival is overestimated (1 year: 0.90 vs 0.73), because the HR describes people with a history of stroke. In Brazil, MAGGIC predicted 21% 3-year mortality against 33% observed. |
| Respiratory | NHANES 2007–2018 linked to death records, 3,818 patients (deaths to 2019) | 0.78 | 1/3/5-year survival: predicted 0.986/0.955/0.921, observed 0.980/0.948/0.914. |
| Respiratory | Published US cohorts (followed to 2020) | – | Life expectancy at 65 relative to no COPD, by GOLD stage 1–4: predicted 0.91/0.79/0.55/0.44, observed 0.93/0.76/0.61/0.50. |

**On "2020 onwards":**
* The most recent open outcomes are MSK-CHORD (to 2023) and the US pooled cohorts (to 2020).
* NHANES public-use mortality follow-up stops at the end of 2019.
* All other open cardiovascular data predates 2020; recent data requires credentialed access,
  which this project does not use.

## Security and robustness tests

All of these run in CI (`hostile.test.ts`, `xml.test.ts`, `upload.test.ts`).

* **Rejected outright:** external entities (XXE) and entity expansion ("billion laughs"),
  because any DOCTYPE or ENTITY declaration is refused.
* **Nesting:** 100,000 levels of nesting in JSON or XML is rejected without overflowing the
  stack.
* **Prototype keys:** keys and element names such as `__proto__` and `constructor` are treated
  as data. Neither JSON nor XML input can change JavaScript's built-in objects.
* **Wrong files:** binary files, HTML and non-FHIR/C-CDA documents are rejected with a readable
  message.
* **Fuzzing:** 2,800 seeded random mutations of the official HL7 documents. Every one either
  produced a report or raised one of the app's own errors with a readable message. None
  crashed or hung.
* **Display:** text from the file is always shown as text, never as HTML.
* **Production build:** checked in headless Chromium under the strict Content Security Policy.
  It sends nothing anywhere else (`connect-src 'self'`).

## Bugs found by final testing (all fixed and covered by tests)

1. **Cancer codes C7A, C7B, C4A.** ICD-10 has alphanumeric cancer categories: C7A malignant
   neuroendocrine tumours, C7B secondary neuroendocrine tumours, C4A Merkel cell carcinoma. A
   real MIMIC record with C7A and C7B codes was not recognised as cancer. These codes are now
   included, and C7B (and ICD-9 209.7) counts as a distant metastasis.
2. **Undated diagnoses.** Hospital encounter diagnoses (MIMIC) carry no date of their own. They
   are now dated from the start of the hospital visit, and the Reasoning panel says so.
3. **Vaccines read as medications.** C-CDA records immunisations with the same element as
   medicines. They are now excluded.
4. **Inherited property names.** The XML parser looked up entity and attribute names in a way
   that matched JavaScript's inherited properties. `&valueOf;` was accepted, and an element
   named `constructor` caused an unhelpful crash. Lookups now use own properties only.

## Known limitations

These are also stated in each model's `sources.md` and in the app's Reasoning panel.

* US population mortality is used for every patient.
* Some source cohorts are older than current treatment: MAGGIC 1980–2006, ADO 1980s–2000s.
* Cardiovascular hazard ratios are constant across ages.
* Accuracy depends on what the uploaded record contains. Missing inputs are averaged over the
  published population, which widens the range.
