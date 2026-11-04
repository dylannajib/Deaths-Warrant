# Cancer model

## Method

For a patient aged *a*, *d* years after diagnosis, the chance of being alive *t* years from
now is

    S(t) = S_pop(a, t) × R(d + t) / R(d)

* `S_pop`: U.S. population survival for the patient's age and sex (NCHS 2024).
* `R`: SEER relative survival, the cancer's own excess risk. Dividing by `R(d)` accounts for
  the years already survived. After year 10 the year-10 excess hazard continues.
* Curves are chosen by site, stage and age at diagnosis (under 50, 50 to 64, 65 to 74, 75+),
  then rescaled to SEER's 2016 to 2022 five-year survival.

| Layer | Needs | Uses |
|---|---|---|
| `site_stage` | site and stage | SEER site × stage × age |
| `site` | site | SEER site × age |
| `all_sites` | nothing | SEER all sites × age |

From the record:

* **Site:** ICD-10, ICD-9 or SNOMED codes. With several cancers, the worst prognosis is used.
* **Stage:** a metastasis code, TNM M1 or stage IV counts as distant. N1+, stage III or a
  lymph-node metastasis code counts as regional. Stage I to II counts as localized.
* **Years since diagnosis:** from the earliest dated metastasis, else the earliest dated
  diagnosis, else 0.

## Sources

| Source | Licence |
|---|---|
| SEER*Explorer, National Cancer Institute: relative survival, diagnosed 2000 to 2022 and 2016 to 2022. Built by `build_seer.py`. | Public domain |
| Arias E, et al. *United States life tables, 2024.* NVSR 75(5), NCHS. | Public domain |
| SNOMED CT concept ids expanded from `snomed_roots.json` by `python -m general.sources.snomed cancer`. | Free in IHTSDO member countries |
| Jee J, et al. *Nature* 2024, MSK-CHORD. **Testing only.** | CC BY-NC-ND 4.0, not redistributed |

## Validation

| Data | Patients | C-index | 1/3/5-year alive, predicted vs observed |
|---|---|---|---|
| MSK-CHORD (`validate.py`), sequenced 2014 to 2023 | 24,067 | 0.71 | 0.71/0.51/0.42 vs 0.80/0.57/0.46 |
| TCGA (`validate_tcga.py`), diagnosed 2010 to 2013 | 4,709 | 0.74 | 0.83/0.69/0.62 vs 0.89/0.70/0.61 |

For MSK-CHORD patients who died, the predicted 25 to 75% range held the actual years lived for
51% of them (50% is ideal).

Limitations: both test sets only include patients fit for surgery or sequencing, which likely
explains the first-year pessimism. Stage at diagnosis misses later spread unless the record
has a metastasis code.
