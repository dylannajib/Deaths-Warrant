"""Chronic lower respiratory disease: updated ADO index for COPD, otherwise published HRs.

Layers, most specific first:

1. ``ado``: COPD with a recorded FEV1 % predicted. The updated ADO index (age, dyspnoea,
   airflow obstruction, from Puhan et al., BMJ Open 2012) and its published 3-year mortality per
   score, applied as a hazard ratio on population mortality so the curve follows ageing.
2. ``base``: any chronic lower respiratory disease. U.S. population mortality (NCHS 2024)
   multiplied by a published all-cause mortality hazard ratio for each recorded condition.

Dyspnoea missing from the record is averaged over the ADO cohort's distribution. No
coefficient here is fitted to patient-level data. See ``sources.md`` and ``sources.json``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from general.authoring import (
    Condition,
    bands,
    codes,
    load_json,
    snomed_sets,
    validation_results,
)
from general.registry import load_life_table
from general.spec import ModelSpec

HERE = Path(__file__).parent
SNOMED = snomed_sets(HERE)
SOURCES: dict[str, list[dict[str, Any]]] = load_json(HERE, "sources.json")
VALIDATION_FILE = HERE / "validation.json"

# key -> (label, ICD-10 prefixes, ICD-9 prefixes, all-cause mortality HR, source id).
CONDITIONS: dict[str, Condition] = {
    "copd": Condition(
        "COPD (including emphysema and chronic bronchitis)",
        ["J41", "J42", "J43", "J44"],
        ["491", "492", "496"],
        1.80,
        "zhao_2025",
    ),
    "bronchiectasis": Condition("Bronchiectasis", ["J47"], ["494"], 2.2, "quint_2016"),
    "asthma": Condition("Asthma", ["J45", "J46"], ["493"], 1.38, "zhang_2022"),
}
GROUP_ICD10 = [f"J{n}" for n in range(40, 48)]
GROUP_ICD9 = [str(n) for n in range(490, 497)]


def _codes(key: str) -> dict[str, list[str]]:
    return codes(CONDITIONS[key], SNOMED[key])


# ---------------------------------------------------------------- updated ADO index
# Puhan MA et al. BMJ Open 2012;2:e002152, Table 3 (points) and Table 4 (3-year mortality).
ADO_3Y_MORTALITY = [
    0.007,
    0.010,
    0.016,
    0.023,
    0.034,
    0.049,
    0.072,
    0.103,
    0.145,
    0.201,
    0.272,
    0.357,
    0.451,
    0.550,
    0.645,
]


ADO_TERMS = [
    # FEV1 % predicted: <=35 -> 4, 36-50 -> 3, 51-64 -> 2, 65-80 -> 1, >=81 -> 0
    {
        "kind": "bands",
        "input": "fev1_pct",
        "bands": bands([(36, 4), (51, 3), (65, 2), (81, 1), (None, 0)]),
    },
    # mMRC dyspnoea: 0 -> 0, 1-2 -> 1, 3 -> 2, 4 -> 3
    {"kind": "bands", "input": "mmrc", "bands": bands([(1, 0), (3, 1), (4, 2), (None, 3)])},
    # Age: 40-49 -> 0, 50-59 -> 2, 60-69 -> 4, 70-79 -> 5, >=80 -> 7 (under 40 scored as 40-49)
    {
        "kind": "bands",
        "input": "age",
        "bands": bands([(50, 0), (60, 2), (70, 4), (80, 5), (None, 7)]),
    },
]

# ADO cohort (13 914 people with COPD, Table 1): 60% male, mMRC mean 1.1 (SD 1.3), binned to
# the integer grades 0-4 under a normal approximation (tails folded into the end grades).
ADO_MALE = 0.60
MMRC_MEAN, MMRC_SD = 1.1, 1.3


def _mmrc_missing() -> list[dict[str, Any]]:
    def cdf(x: float) -> float:
        return 0.5 * (1 + math.erf((x - MMRC_MEAN) / (MMRC_SD * math.sqrt(2))))

    edges = [-math.inf, 0.5, 1.5, 2.5, 3.5, math.inf]
    return [
        {"value": float(k), "weight": round(cdf(hi) - cdf(lo), 6)}
        for k, (lo, hi) in enumerate(zip(edges, edges[1:], strict=False))
    ]


# ---------------------------------------------------------------- record extraction
FEV1_PCT_LOINC = ["20152-5"]  # FEV1 measured/predicted
MMRC_SNOMED = ["870179002"]  # modified Medical Research Council Dyspnea Scale


def _mmrc_rule() -> dict[str, Any]:
    # SNOMED "MRC Dyspnoea scale grade n" findings: MRC grade n = mMRC grade n - 1.
    grades = [{"value": float(k - 1), "codes": {"snomed": SNOMED[f"mrc_{k}"]}} for k in range(1, 6)]
    return {
        "rule": "first_of",
        "rules": [
            {
                "rule": "observation_number",
                "snomed": MMRC_SNOMED,
                "units": {"": 1, "{score}": 1},
                "max_age_days": 730,
            },
            {"rule": "condition_category", "categories": grades},
        ],
    }


def build() -> ModelSpec:
    present = lambda codes: {"rule": "condition_present", "codes": codes}  # noqa: E731
    spec = {
        "id": "respiratory",
        "name": "Chronic lower respiratory disease",
        "version": "1.0.0",
        "order": 30,
        "description": (
            "COPD with a recorded lung function test uses the updated ADO index (age,"
            " breathlessness, airflow obstruction); otherwise U.S. population mortality is"
            " multiplied by a published hazard ratio for each recorded condition."
        ),
        "group_codes": {
            "icd10": GROUP_ICD10,
            "icd9": GROUP_ICD9,
            "snomed": sorted({c for key in CONDITIONS for c in SNOMED[key]}, key=int),
        },
        "inputs": [
            {
                "id": "age",
                "label": "Age",
                "type": "number",
                "unit": "years",
                "min": 18,
                "max": 120,
                "extract": {"rule": "age"},
            },
            {
                "id": "sex",
                "label": "Sex",
                "type": "enum",
                "values": ["female", "male"],
                "extract": {"rule": "sex"},
                "missing": [
                    {"value": "male", "weight": ADO_MALE},
                    {"value": "female", "weight": round(1 - ADO_MALE, 6)},
                ],
                "source": "puhan_2012",
            },
            *(
                {"id": key, "label": label, "type": "boolean", "extract": present(_codes(key))}
                for key, label in ((k, c.label) for k, c in CONDITIONS.items())
            ),
            {
                "id": "fev1_pct",
                "label": "FEV1 % predicted",
                "type": "number",
                "unit": "%",
                "min": 5,
                "max": 150,
                "extract": {
                    "rule": "observation_number",
                    "loinc": FEV1_PCT_LOINC,
                    "units": {"%": 1, "": 1},
                    "max_age_days": 1095,
                },
                "missing": [],
            },
            {
                "id": "mmrc",
                "label": "Breathlessness (mMRC grade 0-4)",
                "type": "number",
                "min": 0,
                "max": 4,
                "extract": _mmrc_rule(),
                "missing": _mmrc_missing(),
                "source": "puhan_2012",
            },
        ],
        "layers": [
            {
                "id": "ado",
                "label": "COPD: updated ADO index",
                "description": (
                    "The updated ADO index scores age, breathlessness (mMRC) and airflow"
                    " obstruction (FEV1 % predicted); its published 3-year mortality (13,914"
                    " people with COPD in 10 cohorts) sets how much higher your mortality is"
                    " than the general population of your age and sex, which then follows"
                    " normal ageing. Never better than the general population."
                ),
                "requires": ["fev1_pct"],
                "when": {"copd": [True]},
                "survival": {
                    "type": "score_life_table",
                    "time": 3,
                    "survival": [round(1 - m, 6) for m in ADO_3Y_MORTALITY],
                    "terms": ADO_TERMS,
                    "life_table": "us_2024",
                },
                "sources": ["puhan_2012", "nchs_us_2024"],
            },
            {
                "id": "base",
                "label": "Respiratory conditions x population mortality",
                "description": (
                    "U.S. population mortality for your age and sex, multiplied by the published"
                    " all-cause mortality hazard ratio of each recorded condition (COPD,"
                    " bronchiectasis, asthma)."
                ),
                "survival": {
                    "type": "life_table_ph",
                    "life_table": "us_2024",
                    "terms": [
                        {
                            "kind": "category",
                            "input": key,
                            "values": {"true": round(math.log(hr), 6), "false": 0.0},
                        }
                        for key, hr in ((k, c.hr) for k, c in CONDITIONS.items())
                    ],
                },
                "sources": sorted({c.source for c in CONDITIONS.values()} | {"nchs_us_2024"}),
            },
        ],
        "life_tables": {"us_2024": load_life_table("us_2024").model_dump()},
        "validation": validation_results(VALIDATION_FILE),
        "sources": [*SOURCES["model"], *SOURCES["validation"]],
    }
    return ModelSpec.model_validate(spec)


def golden_inputs() -> list[dict[str, Any]]:
    none = {key: False for key in CONDITIONS}
    return [
        {**none, "copd": True, "age": 68, "sex": "male", "fev1_pct": 42, "mmrc": 3},
        {**none, "copd": True, "age": 55, "fev1_pct": 75},
        {**none, "copd": True, "age": 85, "sex": "female", "fev1_pct": 30, "mmrc": 4},
        {**none, "copd": True, "age": 35, "sex": "female", "fev1_pct": 90, "mmrc": 0},
        {**none, "copd": True, "age": 72, "sex": "female"},
        {**none, "asthma": True, "bronchiectasis": True, "age": 60, "sex": "male"},
        {**none, "age": 50},
    ]
