# Cardiovascular model: sources and method

## Layers (the first that fits the record is used)

| Layer | Applies when | Method |
|---|---|---|
| `maggic` | Heart failure and a recorded ejection fraction | MAGGIC integer risk score → published 1- and 3-year mortality |
| `heart_failure` | Heart failure, no ejection fraction | UK survival after diagnosis by age at diagnosis (Taylor 2019), applied as relative survival |
| `base` | Any other cardiovascular disease, or none recorded | U.S. population mortality × published hazard ratio per condition |

**MAGGIC** (Pocock et al., Eur Heart J 2013) scores 13 routine measurements:

* the scored factors are ejection fraction, age (× EF band), systolic blood pressure (× EF band),
  BMI, creatinine, NYHA class, sex, current smoking, diabetes, COPD, heart failure diagnosed
  ≥ 18 months ago, no beta-blocker, and no ACE inhibitor/ARB;
* the integer points come from Figure 2;
* Table 4 gives the probability of death at 1 and 3 years for every score from 0 to 50.

Each score's two published points are joined by a Weibull curve, which also extends it beyond
3 years. Survival is capped so that it is never better than the U.S. general population of the
same age and sex.

When a measurement is missing from the record, it is averaged over the MAGGIC cohort's own
distribution (Table 1):
* continuous variables use a normal mixture of the survivors' and non-survivors' means and SDs;
* categorical variables use the pooled percentages.

If the record lists no medications at all, beta-blocker and ACE-I/ARB use are treated as
unknown, not as "not taken".

**Heart failure without an ejection fraction:** Taylor et al. (BMJ 2019, Table 3) give the
survival at 1, 5, 10 and 15 years after diagnosis for each 10-year age band. These are
converted into relative survival against the U.S. life table, using the cohort's sex mix. The
excess hazard is interpolated between the published years. Survival is conditional on the
years since diagnosis, as in the cancer model.

**Other cardiovascular disease:** each recorded condition multiplies population mortality by
its published all-cause hazard ratio. The conditions combine multiplicatively, which is what
the Emerging Risk Factors Collaboration found for diabetes, MI and stroke.

| Condition | HR | Source |
|---|---|---|
| Coronary heart disease / prior MI | 2.0 | ERFC, JAMA 2015 (age- and sex-adjusted, MI) |
| Stroke | 2.1 | ERFC, JAMA 2015 |
| Diabetes | 1.9 | ERFC, JAMA 2015 |
| Atrial fibrillation or flutter | 1.46 | Odutayo et al., BMJ 2016 (pooled RR; adjustment level varies by study) |
| Peripheral artery disease | 1.68 | Matsushita et al., Atherosclerosis 2022 (PAD without CHD/stroke, multivariable) |
| Cardiomyopathy | 1.48 | Jacobsen et al., Am Heart J Plus 2023 (hypertrophic cardiomyopathy) |

No verified population hazard ratio was found for valvular heart disease, so it adds no extra
risk. The full citations, URLs and licences are in `sources.json`. SNOMED CT sets are expanded
from `snomed_roots.json` by `python -m deaths_warrant.sources.snomed cardiovascular`.

## Validation (`validate.py`, results in `validation.json`)

There is no open patient-level cardiovascular data with outcomes from 2020 onwards; every such
dataset requires credentialed access. The evidence is:

* **UCI heart failure clinical records** (299 real patients, Pakistan 2015, CC BY 4.0; patient
  level).
  * The MAGGIC layer ranks risk well: Harrell's C-index is 0.72.
  * It badly overestimates 6-month survival: 0.93 predicted against 0.65 observed. Every
    patient in this cohort was NYHA class III–IV with systolic dysfunction, but a record
    without NYHA class is averaged over MAGGIC's mostly class I–II cohort.
* **Brazilian outpatients** (n = 866, enrolled 2008–2014; a published external validation of
  the MAGGIC score). MAGGIC predicted 20.9% 3-year mortality against 33.4% observed. This
  model's MAGGIC layer reproduces the MAGGIC table at 1 and 3 years, so this applies directly.
* **First acute stroke, Australia and New Zealand** (n = 313,162, 2008–2017, published).
  * Predicted 1/5/10-year survival is 0.90/0.64/0.44, against observed 0.73/0.53/0.36.
  * The stroke HR describes people living with a *history* of stroke, so deaths soon after an
    acute stroke are not captured. Estimates are only meaningful for people who have survived
    the acute phase.
* **Taylor 2019** by age band: a reproduction check. The heart-failure layer is built from
  these figures, so it matches them exactly. This is not independent evidence.

Known limitations:

* MAGGIC was derived from 1980–2006 studies, before current treatments such as ARNI and SGLT2
  inhibitors. External cohorts disagree on whether it now over- or underestimates risk.
* Constant hazard ratios ignore the fact that excess risk shrinks with age.
* U.S. population mortality is used for every patient.
