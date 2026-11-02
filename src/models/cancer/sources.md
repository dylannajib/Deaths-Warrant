# Cancer model: sources and method

## Method

For a patient aged *a*, *d* years after diagnosis, the probability of being alive *t* years
from now is

    S(t) = S_pop(a, t) × R(d + t) / R(d)

* `S_pop` is U.S. population survival for the patient's age and sex (NCHS 2024 life tables).
* `R` is SEER **relative survival**: the survival of people with the cancer divided by that
  of comparable people in the general population. It isolates the cancer's own excess risk.
  Between whole years the excess cumulative hazard `−ln R` is interpolated linearly. After
  year 10, the year-10 excess hazard is assumed to continue.
* Dividing by `R(d)` makes the estimate conditional on having already survived *d* years.

The curve is chosen by site, SEER summary stage and **age at diagnosis** (`a − d`): under 50,
50–64, 65–74 or 75+. The model has three layers. It uses the most specific layer that the
record supports:

| Layer | Needs | Uses |
|---|---|---|
| `site_stage` | site and stage | SEER site × stage × age-at-diagnosis curve |
| `site` | site | SEER site × age, all stages combined |
| `all_sites` | nothing | SEER all sites combined × age |

**Bringing the curves up to date.** SEER curves by time since diagnosis cover diagnoses from
2000 to 2022, and survival has improved since then. Each curve is rescaled so that its 5-year
value matches SEER's 2016–2022 5-year relative survival: `R'(t) = R(t)^k`, where
`k = ln R5_recent / ln R5_curve`. The value of `k` comes from the age-specific cell when it has
at least 1,000 patients, and from all ages otherwise. It is bounded to [0.5, 1.5]. SEER values
above 100% are capped at 100%, and the curves are forced to be non-increasing.

**Reading the record**

* **Site:** ICD-10, ICD-9 or SNOMED CT diagnosis codes. If the record has several cancers, the
  one with the worst prognosis is used. Histology-defined groups (leukaemia, myeloma,
  lymphoma, mesothelioma) take precedence over the organ, as in SEER.
* **Stage** is taken from the first of these that the record contains:
  1. a distant-metastasis code (ICD-10 C78–C79, ICD-9 197–198, SNOMED metastatic neoplasm);
  2. a TNM M1 category;
  3. AJCC stage group IV;
  4. N1 or higher;
  5. stage group III;
  6. a lymph-node metastasis code (C77, 196);
  7. stage group I–II.

  AJCC stage group I–II maps to SEER "localized", III to "regional" and IV to "distant". This
  is an approximation, because some stage II cancers are node-positive.
* **Years since diagnosis:** from the earliest dated distant-metastasis code if there is one,
  otherwise from the earliest dated diagnosis of the modelled cancer. If neither has a date,
  the patient is assumed newly diagnosed.

## Sources

| Id | Source | Licence |
|---|---|---|
| `seer_explorer` | SEER*Explorer, Surveillance Research Program, National Cancer Institute. SEER 21 registries: relative survival by time since diagnosis (diagnosed 2000–2022) and 5-year relative survival (diagnosed 2016–2022). <https://seer.cancer.gov/statistics-network/explorer/>. Built by `python -m deaths_warrant.sources.seer_explorer` into `seer_relative_survival.json`. | U.S. Government work, public domain; NCI asks to be cited |
| `nchs_us_2024` | Arias E, Xu JQ, Kochanek K. *United States life tables, 2024.* NVSR vol 75 no 5. NCHS. See `../_shared/life_tables/README.md`. | U.S. Government work, public domain |
| SNOMED CT | Descendants of the site and metastasis concepts in `snomed_roots.json`, expanded through the HL7 terminology server (tx.fhir.org) into `snomed_sets.json` by `python -m deaths_warrant.sources.snomed cancer`. Only concept ids are stored. | SNOMED CT; use is free in IHTSDO member countries |
| `msk_chord` | Jee J, et al. *Automated real-world data integration improves cancer outcome prediction.* Nature 2024. MSK-CHORD via cBioPortal (`msk_chord_2024`). **Used for testing only.** | CC BY-NC-ND 4.0; the data is not redistributed |

No coefficient is fitted to patient-level data.

## Validation (`validate.py`, results in `validation.json`)

Validation uses MSK-CHORD: 24,067 real patients at Memorial Sloan Kettering, sequenced from
2014 onwards, with outcomes up to the 9 September 2023 data snapshot. Each patient is
predicted as of their first tumour sequencing, using only age, sex, registry site and stage at
diagnosis, and years since diagnosis. The headline results, from the scenario where a
metastatic first sample counts as distant disease:

* **Discrimination:** Harrell's C-index is 0.71 (0.68 using registry stage only).
* **Calibration:** predicted 1/3/5-year survival is 0.71/0.51/0.42, against observed
  0.80/0.57/0.46.
* **Bias by stage:** the model is pessimistic for distant disease and optimistic for
  localized disease.
* **Years lived:** for patients who died, the predicted 25–75% range contained the actual
  years lived 51% of the time (ideally 50%). The median absolute error was 1.1 years. This
  check is biased towards short survivors.

Known limitations:

* MSK patients are treated at a tertiary cancer centre and are selected for tumour
  sequencing, which is mostly done in advanced disease.
* The stage at diagnosis does not capture later progression unless the record holds a
  metastasis code.
* U.S. population mortality is used for every patient.
