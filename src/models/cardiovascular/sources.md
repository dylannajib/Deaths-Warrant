# Cardiovascular model: sources and method

## Layers (the first that fits the record is used)

| Layer | Applies when | Method |
|---|---|---|
| `maggic_admitted` | Heart failure, a recorded ejection fraction, and a hospital stay for heart failure in the last 180 days | As `maggic`, but an unrecorded NYHA class is taken as IV (Michaels 2020) |
| `maggic` | Heart failure and a recorded ejection fraction | MAGGIC integer risk score → published 1- and 3-year mortality |
| `heart_failure` | Heart failure, no ejection fraction | UK survival after diagnosis by age at diagnosis (Taylor 2019), applied as relative survival |
| `stroke` | A dated stroke | U.S. Medicare survival after acute ischaemic stroke by age (Tong 2021), early deaths shaped by Takashima 2020, applied as relative survival |
| `base` | Any other cardiovascular disease, or none recorded (including an undated stroke) | U.S. population mortality × published hazard ratio per condition |

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

**After a recent heart-failure hospital stay:** a record shows one when a heart-failure
diagnosis is linked to an inpatient stay that began in the last 180 days:
* in FHIR, an Encounter of class IMP, ACUTE, NONAC or SS, or an admission lasting past its first
  day;
* in C-CDA, an inpatient Encounter Activity, or a discharge summary's hospital diagnosis.

MAGGIC's NYHA mix comes mostly from outpatients in class I–II, which does not suit someone
just discharged. Michaels et al. (J Card Fail 2020) validated MAGGIC at hospital discharge by
scoring every patient as NYHA class IV, and even then observed slightly more deaths than
predicted. This layer does the same whenever the record has no NYHA class.

The published MAGGIC table itself is not recalibrated. External validations from 2010 onwards
disagree on the direction of its error:
* modern outpatients are over-predicted: ESC-HF-LT 2011–2013, and FAR NHL below;
* patients after discharge, and the Brazilian cohort, are under-predicted.

No single correction is supported.

**Heart failure without an ejection fraction:** Taylor et al. (BMJ 2019, Table 3) give the
survival at 1, 5, 10 and 15 years after diagnosis for each 10-year age band. These are
converted into relative survival against the U.S. life table, using the cohort's sex mix. The
excess hazard is interpolated between the published years. Survival is conditional on the
years since diagnosis, as in the cancer model.

**Stroke:** a stroke diagnosis with a date uses survival after an acute stroke, conditional on
the years since it.
* Tong et al. (Prev Chronic Dis 2021) give crude 5-year survival by age for 1,019,267 U.S.
  Medicare patients aged 66 or over admitted with an acute ischaemic stroke in 2008–2012:
  64.2% at 66–74, 45.6% at 75–84 and 18.9% at 85 or over.
* These are converted to relative survival against the U.S. life table, using the cohort's
  44.3% male share.
* The 5-year excess hazard is split as in the population-based Shiga stroke register
  (Takashima et al. J Stroke 2020, first-ever strokes in 2011): 42% in the first 28 days
  (13.6% died), the rest evenly over years 1–5, and that rate continues afterwards.
* The 66–74 curve is also used for younger patients, who were not in the Medicare cohort.
* Other recorded conditions are not multiplied in, because the cohort already had the usual
  comorbidities of stroke patients.
* A stroke recorded only as an undated diagnosis, a sequela (I69) or a "history of stroke"
  concept cannot be placed in time. It falls back to the base layer's hazard ratio for a
  history of stroke.
* Haemorrhagic strokes use the same curves. In the Shiga register their 5-year survival was
  similar to ischaemic strokes (55% against 59%). Both stroke test cohorts include all types.

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

Patient-level tests have outcomes from 2010 onwards. Published cohort results are used when
their follow-up runs past 2010, though some began earlier (stroke 2008–2017, Brazil
2008–2014). Each result is labelled with its period.
Open patient-level cardiovascular data is scarce, because most of it requires credentialed
access. No cohort below was used to build the layer it tests.

* **FAR NHL registry, Czech Republic** (1,088 outpatients with ejection fraction < 50%,
  enrolled 2014–2015, followed to 2017; CC BY 4.0; patient level). This is the only open
  dataset with every MAGGIC input, NYHA class included.
  * With all inputs, 74% of patient pairs are ranked correctly (C-index 0.74).
  * Predicted 2-year survival is 79.7% against 85.1% observed: MAGGIC is somewhat
    pessimistic for modern outpatients.
  * Without NYHA class, the C-index is 0.70 and predicted 2-year survival is 78.6%.
  * The registry's outcome combines death, heart transplant and LVAD, and its date is not
    given.
* **UCI heart failure clinical records** (299 hospitalised patients, Pakistan 2015, CC BY 4.0;
  patient level). The C-index is 0.72.
  * 6-month survival is overestimated: 92.8% predicted against 65.4% observed.
  * Taking the recent hospital stay into account (NYHA IV) gives 89.6%. Patients in this
    cohort died far more often than in any MAGGIC validation.
* **Brazilian outpatients** (n = 866, enrolled 2008–2014; a published external validation).
  MAGGIC predicted 20.9% 3-year mortality against 33.4% observed. This model's MAGGIC layer
  reproduces the published MAGGIC table, so the result applies directly.
* **First acute stroke, Australia and New Zealand** (Peng et al. Stroke 2022; n = 313,162,
  2008–2017, published). The stroke layer predicts 1/5/10-year survival of 74.9/51.6/32.9%
  against 73.0/52.8/36.4% observed. The previous constant hazard ratio predicted
  90/64/44%.
* **First-ever stroke, England** (Bray et al. Lancet Public Health 2018; SSNAP, 2013–2016,
  published). Predicted 1-year survival is 72.3% against 73.6% observed.
* **Taylor 2019** is a source of the heart-failure layer, so it is not used as a test. A unit
  test checks that the layer reproduces its published survival for every age band.

Known limitations:

* MAGGIC was derived from 1980–2006 studies, before current treatments such as ARNI and SGLT2
  inhibitors. Its error differs by setting (see above).
* The stroke layer rests on ischaemic strokes in people aged 66 or over (see above for
  haemorrhagic strokes).
* Constant hazard ratios ignore the fact that excess risk shrinks with age.
* U.S. population mortality is used for every patient.
