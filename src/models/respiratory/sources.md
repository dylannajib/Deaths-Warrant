# Chronic lower respiratory disease model: sources and method

## Layers (the first that fits the record is used)

| Layer | Applies when | Method |
|---|---|---|
| `ado` | COPD and a recorded FEV1 % predicted | Updated ADO index → published 3-year mortality, applied as a hazard ratio on population mortality |
| `base` | Any chronic lower respiratory disease, or none recorded | U.S. population mortality × published hazard ratio per condition |

**Updated ADO index** (Puhan et al., BMJ Open 2012; 13,914 people with COPD in 10 cohorts):

| Factor | Bands and points |
|---|---|
| FEV1 % predicted | ≥81: 0; 65–80: 1; 51–64: 2; 36–50: 3; ≤35: 4 |
| mMRC dyspnoea | 0: 0; 1–2: 1; 3: 2; 4: 3 |
| Age | 40–49: 0; 50–59: 2; 60–69: 4; 70–79: 5; ≥80: 7 |

Table 4 gives the 3-year mortality for every score from 0 to 14. ADO publishes only a 3-year
risk, so it is converted into a hazard ratio on the patient's own population mortality:

    HR = −ln S_ADO(3) / H_pop(age, 3), floored at 1

This curve passes through the published 3-year point, follows normal ageing afterwards, and
is never better than the general population.

When breathlessness is not recorded, it is averaged over the ADO cohort's distribution (mean
1.1, SD 1.3, binned to grades 0–4). It is read from SNOMED's mMRC scale observation or from
the MRC dyspnoea grade 1–5 findings (MRC grade *n* = mMRC grade *n* − 1).

**Base layer.** Each recorded condition multiplies population mortality:

| Condition | HR | Source |
|---|---|---|
| COPD | 1.80 | Zhao et al., Int J COPD 2025 (meta-analysis, vs no COPD) |
| Bronchiectasis | 2.2 | Quint et al., Eur Respir J 2016 (UK vs general population; women 2.26, men 2.14) |
| Asthma | 1.38 | Zhang et al., Front Cardiovasc Med 2022 (meta-analysis, vs no asthma) |

Full citations, URLs and licences are in `sources.json`. SNOMED CT sets come from
`snomed_roots.json`; bronchiectasis excludes cystic fibrosis.

## Validation (`validate.py`, results in `validation.json`)

* **NHANES 2007–2018 linked to the National Death Index, deaths through 2019** (U.S.,
  public-use; patient level; tests the base layer).
  * COPD or asthma, n = 3,818:
    * Harrell's C-index is 0.78.
    * Predicted 1/3/5-year survival is 0.986/0.955/0.921, against observed 0.980/0.948/0.914.
  * COPD, n = 1,536: C-index 0.69. Predicted 5-year survival is 0.865, against observed 0.836.
  * Asthma only, n = 2,282: C-index 0.75. Predicted 5-year survival is 0.959, against observed
    0.965.
* **Korean COPD cohort** (Park 2019, n = 14,127; base layer). Predicted 5-year mortality by age
  band, against observed:

  | Age | Predicted | Observed |
  |---|---|---|
  | 40–49 | 0.029 | 0.031 |
  | 50–59 | 0.062 | 0.078 |
  | 60–69 | 0.131 | 0.141 |
  | 70–79 | 0.276 | 0.304 |
  | 80–89 | 0.628 | 0.551 |
* **U.S. NHLBI Pooled Cohorts, followed to 2020** (Bhatt 2026; ADO layer). Life expectancy at
  65 relative to no COPD, predicted against observed:

  | GOLD stage | Predicted | Observed |
  |---|---|---|
  | 1 | 0.91 | 0.93 |
  | 2 | 0.79 | 0.76 |
  | 3 | 0.55 | 0.61 |
  | 4 | 0.44 | 0.50 |

Known limitations:

* NHANES diagnoses are self-reported, NHANES has no bronchiectasis question, and the
  public-use follow-up stops at 2019.
* ADO cohorts date from the 1980s–2000s.
* U.S. population mortality is used for every patient.
