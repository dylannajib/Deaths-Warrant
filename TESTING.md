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

**Python: 60 tests (`src/backend/tests/`)**

* Every malformed model spec is rejected when it is exported.
* The evaluator matches hand-worked closed-form results for every survival form, including
  mixing over missing inputs, conditional survival and the population cap.
* The NCHS life table reproduces the published life expectancy at 65 and 80 to within
  0.02 years.
* MAGGIC, ADO and SEER reproduce their published tables exactly.
* Exports are deterministic, and CI fails if they are stale.

**TypeScript: 128 tests (`src/frontend/src/`)**

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
  * A heart-failure hospital stay in the 180 days before the newest entry was found for
    18/24 heart-failure patients.
  * MIMIC has no echocardiography results and its lab codes are not LOINC, so no ejection
    fraction or creatinine was found. MAGGIC therefore never applied, and those patients used
    the heart-failure-by-age layer, as designed.

This test checks robustness on real records; it is not an accuracy test. Accuracy is below.

## Accuracy on real, published patient data

No model was fitted to any of these datasets. Every test cohort has outcomes from 2010 onwards.

There are two measures:
* **Ranking (C-index):** the share of patient pairs that the model put in the right order.
  50% is a coin flip and 100% is perfect.
* **Calibration:** predicted against observed percentage alive.

| Model | Data (period) | Ranking | Calibration: predicted vs observed alive |
|---|---|---|---|
| Cancer | MSK-CHORD, 24,067 patients (sequenced from 2014, outcomes to Sep 2023) | 71% (68% using registry stage only) | 1/3/5 years: 71/51/42% vs 80/57/46%. For patients who died, the predicted 25–75% range held the actual years lived for 51% of them (50% is ideal). |
| Cancer | TCGA, 4,709 patients (diagnosed 2010–2013) | 74% | 1/3/5 years: 83/69/62% vs 89/70/61% |
| Heart failure | FAR NHL registry, 1,088 outpatients (Czech Republic, 2014–2017) | 74% (70% without NYHA class) | 2 years: 79.7% vs 85.1% (outcome: death, transplant or LVAD) |
| Heart failure | UCI records, 299 hospitalised patients (Pakistan, 2015) | 72% | 6 months: 89.6% (with the hospital stay recorded; 92.8% without) vs 65.4% |
| Heart failure | Brazilian MAGGIC validation (published, 2008–2014) | – | 3-year mortality: 20.9% vs 33.4% |
| Stroke | Australia and New Zealand, 313,162 first strokes (published, 2008–2017) | – | 1/5/10 years: 74.9/51.6/32.9% vs 73.0/52.8/36.4% |
| Stroke | England SSNAP, first-ever strokes (published, 2013–2016) | – | 1 year: 72.3% vs 73.6% |
| Respiratory | NHANES 2007–2018 linked to death records, 3,818 patients (deaths to 2019) | 78% | 1/3/5 years: 98.6/95.5/92.1% vs 98.0/94.8/91.4% |
| Respiratory | Published US cohorts (followed to 2020) | – | Life expectancy at 65 relative to no COPD, by GOLD stage 1–4: 91/79/55/44% vs 93/76/61/50% |

**The test window (2010 onwards):**
* The window was widened from 2020 onwards to 2010 onwards on 2026-11-03.
* Open data with outcomes from 2020 onwards exists only for cancer (MSK-CHORD) and for US
  COPD cohorts. All other recent data requires credentialed access, which this project does
  not use.
* Patients from 2010–2015 were treated with somewhat older therapies, so each result keeps its
  period.

**Changes after testing, from published sources only:**
* **Stroke:** the constant hazard ratio was replaced by survival after an acute stroke by age
  (U.S. Medicare 2008–2012, with the early-death share from the Shiga register). Its error
  against Australia/New Zealand fell from 17 to 2 points at 1 year. Both stroke test cohorts
  are independent of these sources.
* **Recent heart-failure hospital stay:** a stay in the last 180 days is now read from the
  record, and an unrecorded NYHA class is then taken as IV (Michaels 2020).
* **MAGGIC was not recalibrated,** because 2010+ validations disagree on the direction of its
  error. FAR NHL shows modern outpatients are slightly over-predicted, while UCI and Brazil are
  under-predicted.
* **Cancer's first-year pessimism** appears in both MSK-CHORD and TCGA. Both select patients
  fit enough for surgery or sequencing, so it was documented, not tuned away.

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
* The stroke layer rests on ischaemic strokes in people aged 66 or over (U.S. Medicare).
* Cardiovascular hazard ratios are constant across ages.
* Accuracy depends on what the uploaded record contains. Missing inputs are averaged over the
  published population, which widens the range.
