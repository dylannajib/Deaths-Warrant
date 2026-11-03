"""Cancer: SEER relative survival on top of U.S. population mortality.

Survival = (population survival for the patient's age and sex, NCHS 2024 life tables)
         x (SEER relative survival for the cancer site, stage and age at diagnosis),
conditional on the years already survived since diagnosis. Three layers, most specific first:

1. site x SEER summary stage x age at diagnosis;
2. site x age at diagnosis (all stages combined), when the stage is not recorded;
3. all cancer sites combined x age at diagnosis, when no site-specific diagnosis is recorded.

Data: ``seer_relative_survival.json`` (``python -m deaths_warrant.sources.seer_explorer``) and
``snomed_sets.json`` (``python -m deaths_warrant.sources.snomed cancer``). See ``sources.md``.
No coefficient here is fitted to patient-level data.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from deaths_warrant.authoring import load_json, snomed_sets, validation_results
from deaths_warrant.registry import load_life_table
from deaths_warrant.spec import ModelSpec

HERE = Path(__file__).parent
SEER: dict[str, Any] = load_json(HERE, "seer_relative_survival.json")
SNOMED = snomed_sets(HERE)
VALIDATION_FILES = [HERE / "validation.json", HERE / "validation_tcga.json"]

# Site key -> (label, ICD-10 prefixes, ICD-9 prefixes). Order is the matching priority when a
# record has several cancers: histology-defined groups first (a lymphoma of the lung is a
# lymphoma, as in SEER), then solid sites from worst to best prognosis, so the cancer that
# dominates survival is the one modelled.
SITES: dict[str, tuple[str, list[str], list[str]]] = {
    "leukaemia": (
        "Leukaemia",
        ["C91", "C92", "C93", "C94", "C95"],
        ["204", "205", "206", "207", "208"],
    ),
    "myeloma": ("Myeloma", ["C90"], ["2030"]),
    "nhl": ("Non-Hodgkin lymphoma", ["C82", "C83", "C84", "C85", "C86"], ["200", "202"]),
    "hodgkin": ("Hodgkin lymphoma", ["C81"], ["201"]),
    "mesothelioma": ("Mesothelioma", ["C45"], ["163"]),
    "pancreas": ("Pancreas", ["C25"], ["157"]),
    "liver": ("Liver and intrahepatic bile duct", ["C22"], ["155"]),
    "lung": ("Lung and bronchus", ["C33", "C34"], ["162"]),
    "esophagus": ("Oesophagus", ["C15"], ["150"]),
    "stomach": ("Stomach", ["C16"], ["151"]),
    "brain": ("Brain and other nervous system", ["C70", "C71", "C72"], ["191", "192"]),
    "gallbladder": ("Gallbladder", ["C23"], ["1560"]),
    "ovary": ("Ovary", ["C56"], ["183"]),
    "bone": ("Bones and joints", ["C40", "C41"], ["170"]),
    "soft_tissue": ("Soft tissue including heart", ["C47", "C49"], ["171"]),
    "small_intestine": ("Small intestine", ["C17"], ["152"]),
    "bladder": ("Urinary bladder", ["C67"], ["188"]),
    "anus": ("Anus, anal canal and anorectum", ["C21"], ["1542", "1543"]),
    "colorectal": ("Colon and rectum", ["C18", "C19", "C20"], ["153", "1540", "1541", "1548"]),
    "cervix": ("Cervix uteri", ["C53"], ["180"]),
    "kidney": ("Kidney and renal pelvis", ["C64", "C65"], ["189"]),
    "larynx": ("Larynx", ["C32"], ["161"]),
    "oral": (
        "Oral cavity and pharynx",
        [f"C{n:02d}" for n in range(15)],
        [str(n) for n in range(140, 150)],
    ),
    "uterus": ("Corpus and uterus", ["C54", "C55"], ["179", "182"]),
    "breast": ("Breast", ["C50"], ["174", "175"]),
    "melanoma": ("Melanoma of the skin", ["C43"], ["172"]),
    "prostate": ("Prostate", ["C61"], ["185"]),
    "testis": ("Testis", ["C62"], ["186"]),
    "thyroid": ("Thyroid", ["C73"], ["193"]),
}
OTHER = "other"  # any other invasive cancer: SEER "all sites combined"
# Invasive primaries outside SITES. Excludes non-melanoma skin cancer (ICD-10 C44, ICD-9 173),
# which SEER does not register, and secondary neoplasms (C77-C79, C7B; 196-198, 209.7).
# ICD-10-CM adds alphanumeric categories: C4A Merkel cell carcinoma, C7A malignant
# neuroendocrine tumours (found missing by the MIMIC-IV end-to-end tests).
OTHER_ICD10 = [f"C{n:02d}" for n in range(98) if n not in (44, 77, 78, 79)] + ["C4A", "C7A"]
OTHER_ICD9 = [str(n) for n in range(140, 210) if n not in (173, 196, 197, 198)]
METASTASIS_DISTANT = {
    "icd10": ["C78", "C79", "C7B"],  # C7B: secondary neuroendocrine tumours
    "icd9": ["197", "198", "2097"],
    "snomed": SNOMED["metastasis_distant"],
}
METASTASIS_NODAL = {"icd10": ["C77"], "icd9": ["196"], "snomed": SNOMED["metastasis_lymph_node"]}

STAGES = ["localized", "regional", "distant"]
AGE_BANDS = [("lt50", 50.0), ("50_64", 65.0), ("65_74", 75.0), ("75plus", None)]
AGE_LABELS = {"lt50": "under 50", "50_64": "50-64", "65_74": "65-74", "75plus": "75+"}

# AJCC stage groups (TNM) map to SEER summary stage approximately: I-II localized, III
# regional, IV distant. Stage II includes some node-positive cancers (e.g. breast IIB), so this
# is a deliberate simplification; M and N categories, when recorded, take precedence.
STAGE_GROUP_LOINC = ["21908-9", "21902-2", "21914-7"]  # clinical, pathological, other
DISTANT_M_LOINC = ["21907-1", "21901-4"]
NODES_N_LOINC = ["21906-3", "21900-6"]

# Recency: SEER curves (diagnosed 2000-2022) are rescaled so their 5-year relative survival
# matches diagnoses in 2016-2022, i.e. R'(t) = R(t)^k with k = ln R5_recent / ln R5_curve.
# k comes from the age-specific cell when it has >= 1000 patients, else from all ages, and is
# bounded to [0.5, 1.5] so a small cell cannot distort the curve.
MIN_CELL_FOR_RECENCY = 1000
RECENCY_BOUNDS = (0.5, 1.5)
NEAR_ONE = 0.995  # ln R ~ 0: no meaningful excess mortality to rescale


def _text_variants(labels: list[str]) -> list[str]:
    return sorted({v for label in labels for v in (label, f"stage {label}")})


def _stage_group_values(group: str, roman: str, snomed: list[str]) -> dict[str, str]:
    """Value keys for AJCC stage group ``roman`` (e.g. "IV") and its sub-stages."""
    arabic = str(["I", "II", "III", "IV"].index(roman) + 1)
    labels = [p + s for p in (roman, arabic) for s in ("", "a", "b", "c", "a1", "a2", "a3")]
    keys = {f"text:{t.lower()}" for t in _text_variants(labels)}
    keys |= {f"other:{label.upper()}" for label in labels} | {f"other:{label}" for label in labels}
    keys |= {f"snomed:{code}" for code in snomed}
    return dict.fromkeys(sorted(keys), group)


def _tnm_values(prefix: str, categories: list[str], group: str) -> dict[str, str]:
    """Value keys for TNM categories such as M1a, cM1, pN2b."""
    labels = [f"{p}{prefix}{c}" for p in ("", "c", "p", "y", "yp", "yc") for c in categories]
    keys = {f"text:{label.lower()}" for label in labels}
    keys |= {f"other:{label}" for label in labels} | {f"other:{label.upper()}" for label in labels}
    return dict.fromkeys(sorted(keys), group)


def _site_categories() -> list[dict[str, Any]]:
    cats = [
        {"value": key, "codes": {"icd10": icd10, "icd9": icd9, "snomed": SNOMED[key]}}
        for key, (_, icd10, icd9) in SITES.items()
    ]
    cats.append({"value": OTHER, "codes": {"icd10": OTHER_ICD10, "icd9": OTHER_ICD9}})
    return cats


def _stage_rule() -> dict[str, Any]:
    def coded(loinc: list[str], values: dict[str, str]) -> dict[str, Any]:
        return {"rule": "observation_coded", "loinc": loinc, "values": values}

    def condition(value: str, codes: dict[str, list[str]]) -> dict[str, Any]:
        return {"rule": "condition_category", "categories": [{"value": value, "codes": codes}]}

    stage_iv = _stage_group_values("distant", "IV", SNOMED["stage_4"])
    stage_iii = _stage_group_values("regional", "III", SNOMED["stage_3"])
    stage_i_ii = {
        **_stage_group_values("localized", "I", SNOMED["stage_1"]),
        **_stage_group_values("localized", "II", SNOMED["stage_2"]),
    }
    return {
        "rule": "first_of",
        "rules": [  # most decisive evidence first
            condition("distant", METASTASIS_DISTANT),
            coded(DISTANT_M_LOINC, _tnm_values("M", ["1", "1a", "1b", "1c", "1d"], "distant")),
            coded(STAGE_GROUP_LOINC, stage_iv),
            coded(
                NODES_N_LOINC,
                _tnm_values(
                    "N",
                    ["1", "1a", "1b", "1c", "2", "2a", "2b", "2c", "3", "3a", "3b", "3c"],
                    "regional",
                ),
            ),
            coded(STAGE_GROUP_LOINC, stage_iii),
            condition("regional", METASTASIS_NODAL),
            coded(STAGE_GROUP_LOINC, stage_i_ii),
        ],
    }


def _cell(site: str, age: str, stage: str) -> tuple[dict[str, Any], str]:
    """The SEER cell to use, falling back to pooled ages, then pooled stages."""
    seer_site = "all" if site == OTHER else site
    for a, s, note in (
        (age, stage, ""),
        ("all", stage, "SEER age-specific estimate unavailable; all ages at diagnosis used."),
        (age, "all", "SEER stage-specific estimate unavailable; all stages combined used."),
        ("all", "all", "SEER estimate unavailable for this group; site total used."),
    ):
        cell = SEER["sites"][seer_site][a][s]
        if None not in cell["curve"]:
            return cell, note
    raise ValueError(f"no SEER curve for {site}")


def _recency_k(cell: dict[str, Any], pooled: dict[str, Any]) -> float:
    source = cell if (cell["n"] or 0) >= MIN_CELL_FOR_RECENCY and cell["recent_5y"] else pooled
    r5, recent = min(1.0, source["curve"][4]), source["recent_5y"]
    if recent is None or r5 >= NEAR_ONE or recent >= NEAR_ONE:
        return 1.0
    lo, hi = RECENCY_BOUNDS
    return min(hi, max(lo, math.log(recent) / math.log(r5)))


def relative_curve(site: str, age: str, stage: str) -> tuple[list[float], str]:
    """Recency-calibrated, monotone relative survival at years 1..10 and any fallback note."""
    cell, note = _cell(site, age, stage)
    pooled, _ = _cell(site, "all", stage)
    k = _recency_k(cell, pooled)
    out, prev = [], 1.0
    for r in cell["curve"]:
        prev = min(prev, min(1.0, r) ** k)  # SEER can exceed 100%; survival never rises
        out.append(round(prev, 6))
    return out, note


def _curves(site_keys: list[str], stages: list[str] | None) -> list[dict[str, Any]]:
    curves = []
    for site in site_keys:
        for stage in stages or ["all"]:
            match = {"site": site} if stages is None else {"site": site, "stage": stage}
            if not site_keys[0]:  # all-sites layer: no keys
                match = {}
            for age, age_lt in AGE_BANDS:
                relative, note = relative_curve(site or OTHER, age, stage)
                curves.append(
                    {"match": match, "age_lt": age_lt, "relative": relative, "note": note}
                )
    return curves


def _layer(
    layer_id: str,
    label: str,
    description: str,
    requires: list[str],
    keys: list[str],
    curves: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": layer_id,
        "label": label,
        "description": description,
        "requires": requires,
        "survival": {
            "type": "relative_survival",
            "life_table": "us_2024",
            "since_input": "since",
            "keys": keys,
            "curves": curves,
        },
        "sources": ["seer_explorer", "nchs_us_2024"],
    }


EXTRAPOLATION = (
    " SEER publishes survival up to 10 years after diagnosis; beyond that the 10th year's"
    " excess mortality is assumed to continue."
)


def build() -> ModelSpec:
    site_values = [*SITES, OTHER]
    spec = {
        "id": "cancer",
        "name": "Cancer",
        "version": "1.0.0",
        "order": 10,
        "description": (
            "Population mortality for your age and sex combined with U.S. SEER cancer survival"
            " for your cancer site, stage and age at diagnosis, allowing for the time you have"
            " already survived since diagnosis."
        ),
        "group_codes": {
            "icd10": sorted(
                {p for _, icd10, _ in SITES.values() for p in icd10}
                | set(OTHER_ICD10)
                | set(METASTASIS_DISTANT["icd10"])
                | set(METASTASIS_NODAL["icd10"])
            ),
            "icd9": sorted(
                {p for _, _, icd9 in SITES.values() for p in icd9}
                | set(OTHER_ICD9)
                | set(METASTASIS_DISTANT["icd9"])
                | set(METASTASIS_NODAL["icd9"])
            ),
            "snomed": sorted(
                {
                    c
                    for key in [*SITES, "metastasis_distant", "metastasis_lymph_node"]
                    for c in SNOMED[key]
                },
                key=int,
            ),
        },
        "inputs": [
            {
                "id": "age",
                "label": "Age",
                "type": "number",
                "unit": "years",
                "min": 0,
                "max": 120,
                "extract": {"rule": "age"},
            },
            {
                "id": "sex",
                "label": "Sex",
                "type": "enum",
                "values": ["female", "male"],
                "extract": {"rule": "sex"},
                "missing": [{"value": "female", "weight": 1}, {"value": "male", "weight": 1}],
            },
            {
                "id": "site",
                "label": "Cancer site",
                "type": "enum",
                "values": site_values,
                "extract": {"rule": "condition_category", "categories": _site_categories()},
                "missing": [],
            },
            {
                "id": "stage",
                "label": "Stage (SEER summary stage)",
                "type": "enum",
                "values": STAGES,
                "extract": _stage_rule(),
                "missing": [],
            },
            {
                "id": "since",
                "label": "Years since diagnosis",
                "type": "number",
                "unit": "years",
                "min": 0,
                "max": 100,
                "extract": {
                    "rule": "first_of",
                    "rules": [
                        {"rule": "years_since_condition", "codes": METASTASIS_DISTANT},
                        {"rule": "years_since_category", "categories": _site_categories()},
                    ],
                },
                # Undated diagnosis: assume newly diagnosed (no credit for time already survived).
                "missing": [{"value": 0, "weight": 1}],
            },
        ],
        "layers": [
            _layer(
                "site_stage",
                "Cancer site and stage (SEER)",
                "Relative survival for your cancer site, stage and age at diagnosis, diagnosed"
                " in the U.S. 2000-2022 and rescaled to 2016-2022 5-year survival. A recorded"
                " distant metastasis counts as distant stage, timed from the metastasis."
                + EXTRAPOLATION,
                ["site", "stage"],
                ["site", "stage"],
                _curves(site_values, STAGES),
            ),
            _layer(
                "site",
                "Cancer site, all stages (SEER)",
                "Your stage was not found in the record, so survival for all stages of your"
                " cancer site combined is used; the range is therefore wider." + EXTRAPOLATION,
                ["site"],
                ["site"],
                _curves(site_values, None),
            ),
            _layer(
                "all_sites",
                "All cancers combined (SEER)",
                "No cancer diagnosis was found in the record, so survival for all cancer sites"
                " combined is used. This is the least specific estimate." + EXTRAPOLATION,
                [],
                [],
                _curves([""], None),
            ),
        ],
        "life_tables": {"us_2024": load_life_table("us_2024").model_dump()},
        "validation": validation_results(*VALIDATION_FILES),
        "sources": [
            {
                "id": "seer_explorer",
                "citation": (
                    "SEER*Explorer: An interactive website for SEER cancer statistics."
                    " Surveillance Research Program, National Cancer Institute. SEER 21"
                    f" registries; relative survival retrieved {SEER['retrieved']}."
                ),
                "url": "https://seer.cancer.gov/statistics-network/explorer/",
                "licence": "U.S. Government work (public domain); citation requested by NCI",
            },
            {
                "id": "nchs_us_2024",
                "citation": (
                    "Arias E, Xu JQ, Kochanek K. United States life tables, 2024. National Vital"
                    " Statistics Reports vol 75 no 5. National Center for Health Statistics."
                ),
                "url": "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/NVSR/75-05/",
                "licence": "U.S. Government work (public domain)",
            },
            {
                "id": "msk_chord",
                "citation": (
                    "Jee J, et al. Automated real-world data integration improves cancer outcome"
                    " prediction. Nature 2024. MSK-CHORD dataset via cBioPortal (msk_chord_2024)."
                ),
                "url": "https://www.cbioportal.org/study/summary?id=msk_chord_2024",
                "licence": "CC BY-NC-ND 4.0 (used for testing only; data not redistributed)",
            },
            {
                "id": "tcga_gdc",
                "citation": (
                    "The Cancer Genome Atlas (TCGA) Research Network. Clinical data harmonised by"
                    " the NCI Genomic Data Commons (Grossman RL, et al. N Engl J Med"
                    " 2016;375:1109-1112), via cBioPortal (studies *_tcga_gdc)."
                ),
                "url": "https://www.cbioportal.org/datasets",
                "licence": "NCI GDC open-access tier (used for testing only; not redistributed)",
            },
        ],
    }
    return ModelSpec.model_validate(spec)


def golden_inputs() -> list[dict[str, Any]]:
    return [
        {"age": 67, "sex": "male", "site": "lung", "stage": "distant", "since": 0},
        {"age": 58, "sex": "female", "site": "breast", "stage": "regional", "since": 4.5},
        {"age": 30, "sex": "male", "site": "testis", "stage": "localized", "since": 12},
        {"age": 72, "site": "leukaemia", "stage": "regional"},
        {"age": 49, "sex": "female", "site": "colorectal", "since": 1},
        {"age": 80, "sex": "male", "site": "other"},
        {"age": 64},
        {"age": 90, "sex": "female", "since": 30},
    ]
