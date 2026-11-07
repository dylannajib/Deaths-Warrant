"""Cardiovascular disease: MAGGIC for heart failure, otherwise life table x published HRs.

Layers, most specific first:

1. ``maggic_admitted``: as ``maggic``, after a hospital stay for heart failure in the last 180
   days. An unrecorded NYHA class is taken as IV, as Michaels et al. (J Card Fail 2020) did for
   patients discharged after heart failure, instead of averaging over MAGGIC's outpatients.
2. ``maggic``: heart failure with a recorded ejection fraction. The MAGGIC integer risk score
   (Pocock et al., Eur Heart J 2013) and its published 1- and 3-year mortality (Table 4),
   joined by a Weibull per score and never better than U.S. population survival.
3. ``heart_failure``: heart failure without an ejection fraction (Taylor et al. BMJ 2019).
4. ``stroke``: a dated stroke. Survival after an acute ischaemic stroke by age (Tong et al. Prev
   Chronic Dis 2021, U.S. Medicare 2008-2012), with the share of excess deaths in the first
   28 days taken from a population-based stroke register (Takashima et al. J Stroke 2020),
   conditional on the years since the stroke.
5. ``base``: any cardiovascular disease. U.S. population mortality (NCHS 2024) multiplied by
   published all-cause mortality hazard ratios for each recorded condition. The conditions
   combine multiplicatively, as reported by the Emerging Risk Factors Collaboration.

MAGGIC inputs missing from the record are averaged over the MAGGIC cohort's own distribution
(Table 1). No coefficient here is fitted to patient-level data. See ``sources.md``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from general.authoring import (
    NCHS_US_2024,
    Condition,
    bands,
    codes,
    condition_present,
    group_codes,
    hr_term,
    load_json,
    population_survival,
    snomed_sets,
    validation_results,
)
from general.registry import load_life_table
from general.spec import ModelSpec

HERE = Path(__file__).parent
SNOMED = snomed_sets(HERE)
VALIDATION_FILE = HERE / "validation.json"

# ---------------------------------------------------------------- diagnoses
# key -> (label, ICD-10 prefixes, ICD-9 prefixes, all-cause mortality HR, source id). Heart
# failure has no HR: it always uses a heart-failure layer (MAGGIC or Taylor 2019 survival).
CONDITIONS: dict[str, Condition] = {
    "heart_failure": Condition(
        "Heart failure",
        ["I50", "I110", "I130", "I132"],
        ["428", "40201", "40211", "40291", "40401", "40403", "40411", "40413", "40491", "40493"],
        None,
        "taylor_2019",
    ),
    "coronary": Condition(
        "Coronary heart disease or prior myocardial infarction",
        ["I20", "I21", "I22", "I23", "I24", "I25"],
        ["410", "411", "412", "413", "414"],
        2.0,
        "erfc_2015",
    ),
    "stroke": Condition(
        "Stroke",
        ["I60", "I61", "I62", "I63", "I64", "I69"],
        ["430", "431", "432", "433", "434", "436", "438"],
        2.1,
        "erfc_2015",
    ),
    "atrial_fibrillation": Condition(
        "Atrial fibrillation or flutter",
        ["I48"],
        ["42731", "42732"],
        1.46,
        "odutayo_2016",
    ),
    "peripheral_artery": Condition(
        "Peripheral artery disease",
        ["I702", "I739"],
        ["4402", "4439"],
        1.68,
        "matsushita_2022",
    ),
    "cardiomyopathy": Condition("Cardiomyopathy", ["I42", "I43"], ["425"], 1.48, "jacobsen_2023"),
}
# Scored, but not part of the group: diabetes alone is not cardiovascular disease.
DIABETES = Condition("Diabetes", ["E10", "E11", "E12", "E13", "E14"], ["250"], 1.9, "erfc_2015")
COPD = {"icd10": ["J43", "J44"], "icd9": ["491", "492", "496"], "snomed": SNOMED["copd"]}
HF_CODES = codes(CONDITIONS["heart_failure"], SNOMED["heart_failure"])

# A stroke itself, without sequelae (I69, ICD-9 438) or "history of stroke" SNOMED concepts.
STROKE_EVENT_CODES = {
    "icd10": [c for c in CONDITIONS["stroke"].icd10 if c != "I69"],
    "icd9": [c for c in CONDITIONS["stroke"].icd9 if c != "438"],
    "snomed": SNOMED["stroke_event"],
}


# ---------------------------------------------------------------- MAGGIC (Pocock et al. 2013)
# Table 4: predicted probability of death at 1 and 3 years for each integer score 0..50.
# fmt: off
MAGGIC_DEATH = [
    (0.015, 0.039), (0.016, 0.043), (0.018, 0.048), (0.020, 0.052), (0.022, 0.058),
    (0.024, 0.063), (0.027, 0.070), (0.029, 0.077), (0.032, 0.084), (0.036, 0.092),
    (0.039, 0.102), (0.043, 0.111), (0.048, 0.122), (0.052, 0.134), (0.058, 0.146),
    (0.063, 0.160), (0.070, 0.175), (0.077, 0.191), (0.084, 0.209), (0.093, 0.227),
    (0.102, 0.247), (0.111, 0.269), (0.122, 0.292), (0.134, 0.316), (0.147, 0.342),
    (0.160, 0.369), (0.175, 0.397), (0.191, 0.427), (0.209, 0.458), (0.227, 0.490),
    (0.248, 0.523), (0.269, 0.556), (0.292, 0.590), (0.316, 0.625), (0.342, 0.658),
    (0.369, 0.692), (0.398, 0.725), (0.427, 0.756), (0.458, 0.787), (0.490, 0.815),
    (0.523, 0.842), (0.557, 0.866), (0.591, 0.889), (0.625, 0.908), (0.659, 0.926),
    (0.692, 0.941), (0.725, 0.953), (0.757, 0.964), (0.787, 0.973), (0.816, 0.980),
    (0.842, 0.985),
]
# fmt: on


# Figure 2 integer points. Bands are "x < lt", and MAGGIC's "20-24" etc. are integer ranges.
MAGGIC_TERMS: list[dict[str, Any]] = [
    {
        "kind": "bands",
        "input": "ef",
        "bands": bands([(20, 7), (25, 6), (30, 5), (35, 3), (40, 2), (None, 0)]),
    },
    {
        "kind": "grid",
        "input": "ef",
        "by": "age",
        "rows": [
            {
                "lt": 30,
                "bands": bands([(56, 0), (60, 1), (65, 2), (70, 4), (75, 6), (80, 8), (None, 10)]),
            },
            {
                "lt": 40,
                "bands": bands([(56, 0), (60, 2), (65, 4), (70, 6), (75, 8), (80, 10), (None, 13)]),
            },
            {
                "lt": None,
                "bands": bands([(56, 0), (60, 3), (65, 5), (70, 7), (75, 9), (80, 12), (None, 15)]),
            },
        ],
    },
    {
        "kind": "grid",
        "input": "ef",
        "by": "sbp",
        "rows": [
            {
                "lt": 30,
                "bands": bands([(110, 5), (120, 4), (130, 3), (140, 2), (150, 1), (None, 0)]),
            },
            {"lt": 40, "bands": bands([(110, 3), (120, 2), (140, 1), (None, 0)])},
            {"lt": None, "bands": bands([(110, 2), (130, 1), (None, 0)])},
        ],
    },
    {
        "kind": "bands",
        "input": "bmi",
        "bands": bands([(15, 6), (20, 5), (25, 3), (30, 2), (None, 0)]),
    },
    {
        "kind": "bands",
        "input": "creatinine",
        "bands": bands(
            [(90, 0), (110, 1), (130, 2), (150, 3), (170, 4), (210, 5), (250, 6), (None, 8)]
        ),
    },
    {"kind": "category", "input": "nyha", "values": {"I": 0, "II": 2, "III": 6, "IV": 8}},
    {"kind": "category", "input": "sex", "values": {"female": 0, "male": 1}},
    {"kind": "category", "input": "smoker", "values": {"current": 1, "not_current": 0}},
    {"kind": "category", "input": "diabetes", "values": {"true": 3, "false": 0}},
    {"kind": "category", "input": "copd", "values": {"true": 2, "false": 0}},
    {"kind": "bands", "input": "hf_years", "bands": bands([(1.5, 0), (None, 2)])},
    {"kind": "category", "input": "beta_blocker", "values": {"true": 0, "false": 3}},
    {"kind": "category", "input": "acei_arb", "values": {"true": 0, "false": 1}},
]

# Table 1 (alive n = 23 521, died n = 15 851): pooled shares and normal mixtures of the
# continuous variables, used only when the record lacks a value.
N_ALIVE, N_DIED = 23_521, 15_851


def _pooled(alive: float, died: float) -> float:
    return (alive * N_ALIVE + died * N_DIED) / (N_ALIVE + N_DIED)


def _mixture_bands(
    alive: tuple[float, float], died: tuple[float, float], cuts: list[float], reps: list[float]
) -> list[dict[str, Any]]:
    """Weight of each band [cut_k-1, cut_k) under the pooled normal mixture (truncated at 0),
    represented by one value inside the band."""

    def cdf(x: float) -> float:
        return sum(
            n * 0.5 * (1 + math.erf((x - mu) / (sd * math.sqrt(2))))
            for n, (mu, sd) in ((N_ALIVE, alive), (N_DIED, died))
        ) / (N_ALIVE + N_DIED)

    edges = [0.0, *cuts, math.inf]
    mass = [cdf(hi) - cdf(lo) for lo, hi in zip(edges, edges[1:], strict=False)]
    total = sum(mass)
    return [{"value": r, "weight": round(m / total, 6)} for r, m in zip(reps, mass, strict=True)]


def _two(p_true: float, true: Any, false: Any) -> list[dict[str, Any]]:
    return [
        {"value": true, "weight": round(p_true, 6)},
        {"value": false, "weight": round(1 - p_true, 6)},
    ]


MAGGIC_MISSING = {
    "sex": _two(_pooled(0.690, 0.651), "male", "female"),
    "sbp": _mixture_bands(
        (131.0, 21.8), (130.5, 25.6), [110, 120, 130, 140, 150], [100, 115, 125, 135, 145, 160]
    ),
    "bmi": _mixture_bands((27.5, 5.1), (26.0, 5.0), [15, 20, 25, 30], [14, 17.5, 22.5, 27.5, 32]),
    "creatinine": _mixture_bands(
        (109.4, 55.8),
        (126.9, 58.4),
        [90, 110, 130, 150, 170, 210, 250],
        [80, 100, 120, 140, 160, 190, 230, 280],
    ),
    "nyha": [
        {"value": c, "weight": round(_pooled(a, d), 6)}
        for c, a, d in (
            ("I", 0.108, 0.067),
            ("II", 0.538, 0.371),
            ("III", 0.313, 0.428),
            ("IV", 0.041, 0.134),
        )
    ],
    "smoker": _two(_pooled(0.342, 0.290), "current", "not_current"),
    "hf_years": [
        {"value": 3.0, "weight": round(_pooled(0.488, 0.497), 6)},
        {"value": 0.5, "weight": round(1 - _pooled(0.488, 0.497), 6)},
    ],
    "beta_blocker": _two(_pooled(0.404, 0.244), True, False),
    # ACE-I or ARB: Table 1 lists them separately without their overlap, so the sum (an upper
    # bound) is used.
    "acei_arb": _two(_pooled(0.680 + 0.033, 0.605 + 0.043), True, False),
}

# ---------------------------------------------------------------- record extraction
EF_LOINC = ["10230-1", "8806-2", "18043-0"]
NYHA_LOINC = ["88020-3", "88021-1"]
SMOKING_LOINC = ["72166-2"]
ROMAN = ["I", "II", "III", "IV"]
# A heart-failure hospital stay this recent counts as "recently admitted" (Michaels 2020 scored
# patients at discharge, and six months keeps the record close to that setting).
ADMITTED_WITHIN_DAYS = 180


def _nyha_rule() -> dict[str, Any]:
    values: dict[str, str] = {}
    for k, cls in enumerate(ROMAN, start=1):
        for code in SNOMED[f"nyha_{k}"]:
            values[f"snomed:{code}"] = cls
        for label in (cls.lower(), str(k)):
            for text in (label, f"class {label}", f"nyha {label}", f"nyha class {label}"):
                values[f"text:{text}"] = cls
    conditions = [
        {"value": cls, "codes": {"snomed": SNOMED[f"nyha_{k}"]}} for k, cls in enumerate(ROMAN, 1)
    ]
    return {
        "rule": "first_of",
        "rules": [
            {
                "rule": "observation_coded",
                "loinc": NYHA_LOINC,
                "values": values,
                "max_age_days": 365,
            },
            {"rule": "condition_category", "categories": conditions},
        ],
    }


def _smoking_values() -> dict[str, str]:
    values = {f"snomed:{c}": "current" for c in SNOMED["current_smoker"]}
    values |= {"snomed:8517006": "not_current", "snomed:266919005": "not_current"}
    for text in (
        "current every day smoker",
        "current some day smoker",
        "current smoker",
        "smoker",
        "heavy tobacco smoker",
        "light tobacco smoker",
    ):
        values[f"text:{text}"] = "current"
    for text in ("former smoker", "ex-smoker", "never smoker", "never smoked", "non-smoker"):
        values[f"text:{text}"] = "not_current"
    return values


BETA_BLOCKERS = [
    "bisoprolol",
    "carvedilol",
    "metoprolol",
    "nebivolol",
    "atenolol",
    "propranolol",
    "bucindolol",
    "labetalol",
]
ACEI_ARB = [
    "captopril",
    "enalapril",
    "lisinopril",
    "ramipril",
    "perindopril",
    "quinapril",
    "trandolapril",
    "fosinopril",
    "benazepril",
    "cilazapril",
    "moexipril",
    "zofenopril",
    "losartan",
    "valsartan",
    "candesartan",
    "irbesartan",
    "telmisartan",
    "olmesartan",
    "eprosartan",
    "azilsartan",
    "sacubitril",
]


def _number(
    id_: str,
    label: str,
    unit: str,
    lo: float,
    hi: float,
    loinc: list[str],
    units: dict[str, float],
    days: int,
) -> dict[str, Any]:
    return {
        "id": id_,
        "label": label,
        "type": "number",
        "unit": unit,
        "min": lo,
        "max": hi,
        "extract": {
            "rule": "observation_number",
            "loinc": loinc,
            "units": units,
            "max_age_days": days,
        },
        "missing": MAGGIC_MISSING.get(id_, []),
    }


def _boolean(id_: str, label: str, extract: dict[str, Any], missing: list | None = None) -> dict:
    out: dict[str, Any] = {"id": id_, "label": label, "type": "boolean", "extract": extract}
    if missing is not None:
        out["missing"] = missing
    return out


def _inputs() -> list[dict[str, Any]]:
    return [
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
            "missing": MAGGIC_MISSING["sex"],
            "source": "maggic_2013",
        },
        *(
            _boolean(key, c.label, condition_present(codes(c, SNOMED[key])))
            for key, c in CONDITIONS.items()
        ),
        _boolean(
            "diabetes", DIABETES.label, condition_present(codes(DIABETES, SNOMED["diabetes"]))
        ),
        _boolean("copd", "COPD", condition_present(COPD)),
        _number(
            "ef", "Left ventricular ejection fraction", "%", 5, 90, EF_LOINC, {"%": 1, "": 1}, 730
        ),
        {
            **_number(
                "sbp",
                "Systolic blood pressure",
                "mmHg",
                50,
                260,
                ["8480-6"],
                {"mm[hg]": 1, "mmhg": 1, "mm hg": 1},
                365,
            ),
            "source": "maggic_2013",
        },
        {
            **_number(
                "bmi",
                "Body mass index",
                "kg/m2",
                10,
                80,
                ["39156-5"],
                {"kg/m2": 1, "kg/m^2": 1, "kg/(m2)": 1, "": 1},
                365,
            ),
            "source": "maggic_2013",
        },
        {
            **_number(
                "creatinine",
                "Serum creatinine",
                "umol/L",
                20,
                2000,
                ["2160-0", "38483-4", "14682-9"],
                {"mg/dl": 88.4, "umol/l": 1, "µmol/l": 1, "μmol/l": 1, "mmol/l": 1000},
                365,
            ),
            "source": "maggic_2013",
        },
        {
            "id": "nyha",
            "label": "NYHA class",
            "type": "enum",
            "values": ROMAN,
            "extract": _nyha_rule(),
            "missing": MAGGIC_MISSING["nyha"],
            "source": "maggic_2013",
        },
        _boolean(
            "hf_admission",
            f"Hospital stay for heart failure in the last {ADMITTED_WITHIN_DAYS} days",
            {
                **condition_present(HF_CODES),
                "admitted_within_days": ADMITTED_WITHIN_DAYS,
            },
            [{"value": False, "weight": 1.0}],
        ),
        {
            "id": "nyha_admitted",
            "label": "NYHA class (after a heart-failure hospital stay)",
            "type": "enum",
            "values": ROMAN,
            "extract": _nyha_rule(),
            "missing": [{"value": "IV", "weight": 1.0}],
            "source": "michaels_2020",
        },
        {
            "id": "smoker",
            "label": "Current smoker",
            "type": "enum",
            "values": ["current", "not_current"],
            "extract": {
                "rule": "observation_coded",
                "loinc": SMOKING_LOINC,
                "values": _smoking_values(),
            },
            "missing": MAGGIC_MISSING["smoker"],
            "source": "maggic_2013",
        },
        {
            "id": "hf_years",
            "label": "Years since heart failure diagnosis",
            "type": "number",
            "unit": "years",
            "min": 0,
            "max": 100,
            "extract": {"rule": "years_since_condition", "codes": HF_CODES},
            "missing": MAGGIC_MISSING["hf_years"],
            "source": "maggic_2013",
        },
        {
            "id": "stroke_years",
            "label": "Years since the stroke",
            "type": "number",
            "unit": "years",
            "min": 0,
            "max": 100,
            # Sequelae and "history of" codes are dated when recorded, not when the stroke
            # happened, so they cannot time it. Such records use the base layer instead.
            "extract": {"rule": "years_since_condition", "codes": STROKE_EVENT_CODES},
            "missing": [],
        },
        _boolean(
            "beta_blocker",
            "Taking a beta-blocker",
            {"rule": "medication_present", "atc": ["C07"], "names": BETA_BLOCKERS},
            MAGGIC_MISSING["beta_blocker"],
        )
        | {"source": "maggic_2013"},
        _boolean(
            "acei_arb",
            "Taking an ACE inhibitor, ARB or ARNI",
            {"rule": "medication_present", "atc": ["C09"], "names": ACEI_ARB},
            MAGGIC_MISSING["acei_arb"],
        )
        | {"source": "maggic_2013"},
    ]


BASE_CONDITIONS = {
    **{key: c for key, c in CONDITIONS.items() if c.hr is not None},
    "diabetes": DIABETES,
}


# Taylor et al. BMJ 2019, Table 3: survival 1, 5, 10, 15 years after a heart failure diagnosis
# by age at diagnosis (UK, diagnosed 2000-2017, 52.2% male, Table 1).
TAYLOR_SURVIVAL = [  # (age_lt for the band, representative age, {year: survival})
    (55.0, 50, {1: 0.903, 5: 0.785, 10: 0.647, 15: 0.544}),
    (65.0, 60, {1: 0.879, 5: 0.706, 10: 0.528, 15: 0.384}),
    (75.0, 70, {1: 0.835, 5: 0.591, 10: 0.354, 15: 0.172}),
    (85.0, 80, {1: 0.765, 5: 0.432, 10: 0.184, 15: 0.058}),
    (95.0, 90, {1: 0.632, 5: 0.223, 10: 0.044, 15: 0.002}),
    (None, 97, {1: 0.439, 5: 0.060}),
]
TAYLOR_MALE = 0.522


def heart_failure_curves() -> list[dict[str, Any]]:
    """Relative survival after diagnosis by age band, from Taylor 2019 Table 3.

    R(t) = observed survival / population survival at the band's representative age (U.S.
    life table, cohort sex mix). The excess cumulative hazard -ln R is interpolated linearly
    between the published years to give whole-year values. R is kept non-increasing.
    """
    table = load_life_table("us_2024")
    curves = []
    for age_lt, age, published in TAYLOR_SURVIVAL:
        knots = {0: 0.0} | {
            t: -math.log(min(1.0, s / population_survival(table, age, t, TAYLOR_MALE)))
            for t, s in published.items()
        }
        years = sorted(knots)
        relative, prev = [], 1.0
        for k in range(1, years[-1] + 1):
            lo = max(y for y in years if y <= k)
            hi = min(y for y in years if y >= k)
            x = (
                knots[lo]
                if lo == hi
                else knots[lo] + (knots[hi] - knots[lo]) * (k - lo) / (hi - lo)
            )
            prev = min(prev, math.exp(-x))
            relative.append(round(prev, 6))
        curves.append({"match": {}, "age_lt": age_lt, "relative": relative})
    return curves


# Tong et al. Prev Chronic Dis 2021, Tables 1-2: U.S. Medicare fee-for-service beneficiaries aged
# 66 or over admitted with acute ischaemic stroke 2008-2012 (n = 1,019,267, 44.3% male). Crude
# Kaplan-Meier 5-year survival from the stroke by age group.
TONG_SURVIVAL_5Y = [  # (age_lt for the band, representative age, observed 5-year survival)
    (75.0, 70, 0.642),
    (85.0, 80, 0.456),
    (None, 89, 0.189),
]
TONG_MALE = 0.443
# Takashima et al. J Stroke 2020 (Shiga, Japan, first-ever stroke 2011): 296 of 2,176 died
# within 28 days (Table 4 minus Table 2), and the 1,880 28-day survivors had 5-year relative
# survival 0.820 (Table 3). Share of the 5-year excess cumulative hazard in the first 28 days:
EARLY_DAYS = 28
_EARLY = -math.log(1 - 296 / 2176)
STROKE_EARLY_SHARE = _EARLY / (_EARLY - math.log(0.820))


def stroke_curves() -> list[dict[str, Any]]:
    """Relative survival after an acute stroke by age band (Tong 2021 at 5 years).

    The band's 5-year excess cumulative hazard X5 = -ln(observed / population survival) (U.S.
    life table, cohort sex mix) is split as in Takashima 2020: a share in the first 28 days,
    the rest spread evenly to 5 years and continued at that rate afterwards.
    """
    table = load_life_table("us_2024")
    early = EARLY_DAYS / 365.25
    curves = []
    for age_lt, age, observed in TONG_SURVIVAL_5Y:
        x5 = -math.log(observed / population_survival(table, age, 5, TONG_MALE))
        relative = [
            round(
                math.exp(
                    -x5
                    * (STROKE_EARLY_SHARE + (1 - STROKE_EARLY_SHARE) * (k - early) / (5 - early))
                ),
                6,
            )
            for k in range(1, 6)
        ]
        curves.append({"match": {}, "age_lt": age_lt, "relative": relative})
    return curves


# Citations live in sources.json ("model": coefficient sources, "validation": test data).
SOURCES: dict[str, list[dict[str, Any]]] = load_json(HERE, "sources.json")


def build() -> ModelSpec:
    survival_table = [[round(1 - d1, 6), round(1 - d3, 6)] for d1, d3 in MAGGIC_DEATH]
    spec = {
        "id": "cardiovascular",
        "name": "Cardiovascular disease",
        "version": "1.0.0",
        "order": 20,
        "description": (
            "Heart failure with a recorded ejection fraction uses the MAGGIC risk score. Heart "
            "failure without one uses survival by age at diagnosis. A dated stroke uses survival "
            "after stroke by age. Other cardiovascular disease uses U.S. population mortality "
            "multiplied by published hazard ratios."
        ),
        "group_codes": group_codes(CONDITIONS, SNOMED),
        "inputs": _inputs(),
        "layers": [
            {
                "id": "maggic_admitted",
                "label": "Heart failure after a recent hospital stay: MAGGIC risk score",
                "description": (
                    "MAGGIC risk score, applied after a heart failure hospital stay in the last"
                    f" {ADMITTED_WITHIN_DAYS} days. A missing NYHA class is set to IV, following a"
                    " published validation of MAGGIC at hospital discharge (Michaels 2020). That"
                    " study observed slightly more deaths than MAGGIC predicted."
                ),
                "requires": ["ef"],
                "when": {"heart_failure": [True], "hf_admission": [True]},
                "survival": {
                    "type": "score_weibull",
                    "times": [1, 3],
                    "survival": survival_table,
                    "terms": [
                        {**t, "input": "nyha_admitted"} if t["input"] == "nyha" else t
                        for t in MAGGIC_TERMS
                    ],
                    "life_table": "us_2024",
                },
                "sources": ["maggic_2013", "michaels_2020", "nchs_us_2024"],
            },
            {
                "id": "maggic",
                "label": "Heart failure: MAGGIC risk score",
                "description": (
                    "MAGGIC integer risk score from 13 routine measurements. Published 1-year and"
                    " 3-year mortality per score, from 39,372 patients in 30 studies (1980-"
                    "2006). A Weibull curve extends survival past 3 years. Survival is capped at "
                    "general population survival for the same age and sex. Missing measurements "
                    "are averaged over the MAGGIC cohort. This widens the range."
                ),
                "requires": ["ef"],
                "when": {"heart_failure": [True]},
                "survival": {
                    "type": "score_weibull",
                    "times": [1, 3],
                    "survival": survival_table,
                    "terms": MAGGIC_TERMS,
                    "life_table": "us_2024",
                },
                "sources": ["maggic_2013", "nchs_us_2024"],
            },
            {
                "id": "heart_failure",
                "label": "Heart failure: survival by age at diagnosis (UK cohort)",
                "description": (
                    "Ejection fraction not found, so MAGGIC does not apply. Survival after a "
                    "heart failure diagnosis by age at diagnosis, from 55,959 UK patients "
                    "diagnosed 2000-2017. Applied relative to population survival, conditional"
                    " on years since diagnosis. After 15 years (5 years if diagnosed at 95 or "
                    "over), the last published excess mortality is applied."
                ),
                "when": {"heart_failure": [True]},
                "survival": {
                    "type": "relative_survival",
                    "life_table": "us_2024",
                    "since_input": "hf_years",
                    "curves": heart_failure_curves(),
                },
                "sources": ["taylor_2019", "nchs_us_2024"],
            },
            {
                "id": "stroke",
                "label": "Stroke: survival by age at the stroke (U.S. Medicare)",
                "description": (
                    "5-year survival after acute ischaemic stroke by age group, from 1,019,267 "
                    "U.S. Medicare patients aged 66 or over, admitted 2008-2012. Applied "
                    "relative to population survival, conditional on years since the stroke. "
                    "Share of deaths in the first 28 days: Shiga stroke register, Japan, 2011. "
                    "Patients under 66 use the 66 to 74 curve. Haemorrhagic strokes use the same "
                    "curves (5-year survival 55% against 59% for ischaemic strokes in the Shiga "
                    "register). After 5 years, the year 1 to 5 excess mortality is applied. Other"
                    " recorded conditions are not added, because the cohort already included "
                    "them."
                ),
                "requires": ["stroke_years"],
                "when": {"stroke": [True]},
                "survival": {
                    "type": "relative_survival",
                    "life_table": "us_2024",
                    "since_input": "stroke_years",
                    "curves": stroke_curves(),
                },
                "sources": ["tong_2021", "takashima_2020", "nchs_us_2024"],
            },
            {
                "id": "base",
                "label": "Other cardiovascular disease x population mortality",
                "description": (
                    "U.S. population mortality for age and sex, multiplied by the published "
                    "all-cause mortality hazard ratio of each recorded condition: coronary "
                    "disease, stroke, atrial fibrillation, peripheral artery disease, "
                    "cardiomyopathy, diabetes. Ratios for several conditions are multiplied "
                    "(Emerging Risk Factors Collaboration). Each ratio was measured on its own, "
                    "so risk may be overstated when several conditions are present."
                ),
                "survival": {
                    "type": "life_table_ph",
                    "life_table": "us_2024",
                    "terms": [hr_term(key, c.hr) for key, c in BASE_CONDITIONS.items()],
                },
                "sources": [
                    *dict.fromkeys(c.source for c in BASE_CONDITIONS.values()),
                    NCHS_US_2024["id"],
                ],
            },
        ],
        "life_tables": {"us_2024": load_life_table("us_2024").model_dump()},
        "validation": validation_results(VALIDATION_FILE),
        "sources": [*SOURCES["model"], NCHS_US_2024, *SOURCES["validation"]],
    }
    return ModelSpec.model_validate(spec)


def golden_inputs() -> list[dict[str, Any]]:
    hf = {
        "heart_failure": True,
        "hf_admission": False,
        "coronary": False,
        "stroke": False,
        "atrial_fibrillation": False,
        "peripheral_artery": False,
        "cardiomyopathy": False,
    }
    return [
        {
            **hf,
            "age": 72,
            "sex": "male",
            "ef": 25,
            "sbp": 105,
            "bmi": 23,
            "creatinine": 160,
            "nyha": "III",
            "smoker": "not_current",
            "diabetes": True,
            "copd": False,
            "hf_years": 4,
            "beta_blocker": True,
            "acei_arb": True,
        },
        {**hf, "age": 58, "sex": "female", "ef": 55, "diabetes": False, "copd": False},
        {
            **hf,
            "hf_admission": True,
            "age": 77,
            "sex": "female",
            "ef": 30,
            "diabetes": False,
            "copd": False,
        },  # fmt: skip
        {**hf, "age": 85, "ef": 35, "diabetes": False, "copd": True, "creatinine": 300},
        {**hf, "age": 70, "sex": "male", "diabetes": False, "copd": False},
        {
            **hf,
            "heart_failure": False,
            "coronary": True,
            "stroke": True,
            "stroke_years": 2.5,
            "age": 66,
            "sex": "female",
            "diabetes": True,
            "copd": False,
        },
        {
            **hf,
            "heart_failure": False,
            "atrial_fibrillation": True,
            "age": 50,
            "diabetes": False,
            "copd": False,
        },
    ]
