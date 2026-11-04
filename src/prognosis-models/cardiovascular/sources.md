# Cardiovascular model

## Layers (the first that fits is used)

| Layer | When | Method |
|---|---|---|
| `maggic_admitted` | Heart failure, ejection fraction, and a heart-failure hospital stay in the last 180 days | MAGGIC, with a missing NYHA class taken as IV (Michaels 2020) |
| `maggic` | Heart failure and ejection fraction | MAGGIC risk score (Pocock 2013) |
| `heart_failure` | Heart failure, no ejection fraction | UK survival by age at diagnosis (Taylor 2019) |
| `stroke` | A dated stroke | U.S. Medicare survival after stroke by age (Tong 2021), early deaths from the Shiga register (Takashima 2020) |
| `base` | Anything else | U.S. population mortality × hazard ratio per condition |

**MAGGIC** scores 13 measurements (ejection fraction, age, blood pressure, BMI, creatinine,
NYHA class, sex, smoking, diabetes, COPD, heart failure over 18 months, beta-blocker,
ACE inhibitor/ARB). Its published 1- and 3-year mortality per score is joined by a Weibull
curve and capped at population survival. Missing measurements are averaged over the MAGGIC
cohort. If the record lists no medications, medication use counts as unknown.

**Heart failure and stroke** survival tables are turned into relative survival against the
U.S. life table, so the result accounts for the years since diagnosis. Patients under 66 use
the 66 to 74 stroke curve. An undated stroke falls back to the base layer.

**Base layer hazard ratios:**

| Condition | HR | Source |
|---|---|---|
| Coronary heart disease / prior MI | 2.0 | ERFC, JAMA 2015 |
| Stroke | 2.1 | ERFC, JAMA 2015 |
| Diabetes | 1.9 | ERFC, JAMA 2015 |
| Atrial fibrillation or flutter | 1.46 | Odutayo, BMJ 2016 |
| Peripheral artery disease | 1.68 | Matsushita, Atherosclerosis 2022 |
| Cardiomyopathy | 1.48 | Jacobsen, Am Heart J Plus 2023 |

Valvular disease adds no risk (no verified ratio found). Full citations and licences are in
`sources.json`. SNOMED sets come from `snomed_roots.json`.

## Validation (`validate.py`)

| Data | Patients | Result |
|---|---|---|
| FAR NHL, Czech outpatients, 2014 to 2017 | 1,088 | C-index 0.74. 2-year alive 79.7% vs 85.1% |
| UCI, Pakistani inpatients, 2015 | 299 | C-index 0.72. 6-month alive 89.6% vs 65.4% |
| Brazil MAGGIC validation, 2008 to 2014 (published) | 866 | 3-year deaths 20.9% vs 33.4% |
| Australia and New Zealand first strokes, 2008 to 2017 (Peng 2022) | 313,162 | 1/5/10-year alive 74.9/51.6/32.9% vs 73.0/52.8/36.4% |
| England first strokes, 2013 to 2016 (Bray 2018) | SSNAP | 1-year alive 72.3% vs 73.6% |

MAGGIC is not recalibrated: modern outpatients are over-predicted, recent inpatients
under-predicted. Taylor 2019 builds the heart-failure layer, so it is not used to test it.

Limitations: MAGGIC data is from 1980 to 2006, the stroke curves come from ischaemic strokes
at 66+, and hazard ratios are constant across ages.
