# Chronic lower respiratory disease model

## Layers (the first that fits is used)

| Layer | When | Method |
|---|---|---|
| `ado` | COPD and FEV1 % predicted | Updated ADO index (Puhan 2012), as a hazard ratio on population mortality |
| `base` | Anything else | U.S. population mortality × hazard ratio per condition |

**ADO** points:

| Factor | Points |
|---|---|
| FEV1 % predicted | ≥81: 0, 65-80: 1, 51-64: 2, 36-50: 3, ≤35: 4 |
| mMRC breathlessness | 0: 0, 1-2: 1, 3: 2, 4: 3 |
| Age | 40-49: 0, 50-59: 2, 60-69: 4, 70-79: 5, ≥80: 7 |

ADO publishes 3-year mortality per score. It becomes a hazard ratio
`HR = −ln S_ADO(3) / H_pop(age, 3)`, at least 1. Missing breathlessness is averaged over the
ADO cohort.

**Base layer hazard ratios:**

| Condition | HR | Source |
|---|---|---|
| COPD | 1.80 | Zhao, Int J COPD 2025 |
| Bronchiectasis | 2.2 | Quint, Eur Respir J 2016 |
| Asthma | 1.38 | Zhang, Front Cardiovasc Med 2022 |

Full citations and licences are in `sources.json`. SNOMED sets come from `snomed_roots.json`
(bronchiectasis excludes cystic fibrosis).

## Validation (`validate.py`)

| Data | Patients | Result |
|---|---|---|
| NHANES 2011-2018, deaths to 2019 | 2,602 | C-index 0.78. 1/3/5-year alive 98.6/95.5/92.1% vs 98.1/95.2/91.7% |
| Korean COPD cohort, 2003-2013 (Park 2019) | 14,127 | 5-year deaths by age 40s-80s: 3/6/13/28/63% vs 3/8/14/30/55% |
| U.S. pooled cohorts, to 2020 (Bhatt 2026), ADO layer | 45,886 | Life expectancy at 65 vs no COPD, GOLD 1-4: 91/79/55/44% vs 93/76/61/50% |

Limitations: NHANES diagnoses are self-reported and it has no bronchiectasis question. ADO
cohorts date from the 1980s-2000s.
