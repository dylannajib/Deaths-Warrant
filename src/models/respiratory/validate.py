"""Test the chronic lower respiratory disease model on real patients (testing only).

1. Patient level: NHANES 2011-2018 (U.S. national survey) linked to the National Death Index
   through 31 December 2019; public-use files, no registration. Only cycles interviewed from
   2011 are used, so every outcome falls in the 2010+ test window. Download into the
   git-ignored ``data/nhanes/``:
   * DEMO_G..J.XPT and MCQ_G..J.XPT from https://wwwn.cdc.gov/nchs/nhanes/ (cycles 2011-2018);
   * NHANES_<cycle>_MORT_2019_PUBLIC.dat from
     https://ftp.cdc.gov/pub/Health_Statistics/NCHS/datalinkage/linked_mortality/.
   COPD (emphysema, current chronic bronchitis or COPD) and current asthma are self-reported
   doctor diagnoses; NHANES has no bronchiectasis question and its spirometry has no stored
   predicted values, so this tests the base layer.
2. Published cohorts: Korean COPD 5-year mortality by age (Park 2019); U.S. life expectancy at
   65 by GOLD stage relative to no COPD (Bhatt 2026; NHLBI Pooled Cohorts followed to 2020),
   for the ADO layer.

From src/backend:  ../../.venv/bin/python ../models/respiratory/validate.py
Writes ``validation.json`` (aggregate results only, every group n >= 20).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "backend")]  # model.py, deaths_warrant
from model import CONDITIONS, build  # noqa: E402

from deaths_warrant.evaluate import evaluate, population_cum_hazard, survival_function  # noqa: E402
from deaths_warrant.registry import load_life_table  # noqa: E402
from deaths_warrant.sources.xpt import read_xpt  # noqa: E402
from deaths_warrant.validation import (  # noqa: E402
    calibration_at,
    harrell_c,
    kaplan_meier,
    km_median,
    result_row,
    sex_mix,
)

DATA = HERE.parents[2] / "data" / "nhanes"
OUT = HERE / "validation.json"
CYCLES = {  # 2007-2010 cycles excluded: their follow-up starts before the 2010+ window
    "G": "2011_2012",
    "H": "2013_2014",
    "I": "2015_2016",
    "J": "2017_2018",
}
NONE = {key: False for key in CONDITIONS}
YEARS = (1, 3, 5)
MIN_GROUP = 20

# Park et al. Korean J Intern Med 2019: COPD diagnosed 2003-2013, n = 14,127, 58.8% male.
PARK_N, PARK_MALE = 14_127, 0.588
PARK = [  # (band, representative age, share of cohort, observed 5-year mortality)
    ("40-49", 45, 0.067, 0.031),
    ("50-59", 55, 0.146, 0.078),
    ("60-69", 65, 0.275, 0.141),
    ("70-79", 75, 0.331, 0.304),
    ("80-89", 85, 0.182, 0.551),
]
# Bhatt et al. JAMA Intern Med 2026: life expectancy at 65 (years), age-adjusted model.
BHATT_N, BHATT_FEMALE = 45_886, 0.563
BHATT = {"none": 21.5, "GOLD 1": 20.0, "GOLD 2": 16.4, "GOLD 3": 13.1, "GOLD 4": 10.7}
GOLD_FEV1 = {"GOLD 1": 90.0, "GOLD 2": 65.0, "GOLD 3": 40.0, "GOLD 4": 25.0}  # mid-grade FEV1 %


def nhanes_cohort() -> list[dict[str, Any]]:
    people = []
    for letter, cycle in CYCLES.items():
        demo = {r["SEQN"]: r for r in read_xpt(DATA / f"DEMO_{letter}.XPT")}
        mcq = {r["SEQN"]: r for r in read_xpt(DATA / f"MCQ_{letter}.XPT")}
        with open(DATA / f"NHANES_{cycle}_MORT_2019_PUBLIC.dat", encoding="ascii") as f:
            for line in f:
                seqn, elig, mort, months = float(line[0:6]), line[14], line[15], line[42:45].strip()
                d, m = demo.get(seqn), mcq.get(seqn)
                if elig != "1" or not months or d is None or m is None:
                    continue
                age = d["RIDAGEYR"]
                if age is None or not 18 <= age < 80:  # 80 means "80 or over" in NHANES
                    continue
                copd = m.get("MCQ160G") == 1 or m.get("MCQ170K") == 1 or m.get("MCQ160O") == 1
                asthma = m.get("MCQ035") == 1
                if not (copd or asthma):
                    continue
                people.append(
                    {
                        "years": int(months) / 12,
                        "died": mort == "1",
                        "observed": {
                            **NONE,
                            "copd": copd,
                            "asthma": asthma,
                            "age": age,
                            "sex": "male" if d["RIAGENDR"] == 1 else "female",
                        },
                    }
                )
    return people


def nhanes(spec) -> list[dict[str, Any]]:
    people = nhanes_cohort()
    preds = [evaluate(spec, p["observed"]) for p in people]
    dataset = "NHANES 2011-2018 linked to the National Death Index (U.S.)"
    period = "Interviewed 2011-2018, deaths through 31 Dec 2019"
    notes = (
        "Patient-level, predicted at interview from age, sex and self-reported doctor-diagnosed"
        " COPD (emphysema, current chronic bronchitis or COPD) or current asthma (base layer);"
        " ages 18-79, unweighted."
    )
    out = []
    groups = {
        "All with COPD or asthma": lambda o: True,
        "COPD": lambda o: o["copd"],
        "Asthma without COPD": lambda o: o["asthma"] and not o["copd"],
    }
    for name, keep in groups.items():
        pairs = [(p, r) for p, r in zip(people, preds, strict=True) if keep(p["observed"])]
        if len(pairs) < MIN_GROUP:
            continue
        times = [p["years"] for p, _ in pairs]
        events = [p["died"] for p, _ in pairs]
        n = len(pairs)
        medians = [r["median_years"] if r["median_years"] is not None else 60.0 for _, r in pairs]
        out.append(
            result_row(
                dataset,
                period,
                n,
                f"{name}: Harrell's C-index",
                harrell_c(times, events, medians),
                notes,
                "nhanes_lmf_2019",
            )
        )
        for t in YEARS:
            pred, obs = calibration_at(
                t, times, events, [r["survival_at"][str(t)] for _, r in pairs]
            )
            out.append(
                result_row(
                    dataset,
                    period,
                    n,
                    f"{name}: predicted {t}-year survival",
                    pred,
                    notes,
                    "nhanes_lmf_2019",
                )
            )
            out.append(
                result_row(
                    dataset,
                    period,
                    n,
                    f"{name}: observed {t}-year survival (Kaplan-Meier)",
                    obs,
                    notes,
                    "nhanes_lmf_2019",
                )
            )
        km = km_median(kaplan_meier(times, events))
        if km is not None:
            out.append(
                result_row(
                    dataset,
                    period,
                    n,
                    f"{name}: observed median survival (years)",
                    km,
                    notes,
                    "nhanes_lmf_2019",
                )
            )
    return out


def park(spec) -> list[dict[str, Any]]:
    dataset = "Korean National Health Insurance COPD sample (Park et al. 2019)"
    period = "COPD diagnosed 2003-2013"
    notes = (
        "Published cohort: base layer (no lung function), COPD only, at the age band's"
        " representative age with the cohort's sex mix."
    )
    out = []
    for band, age, share, mortality in PARK:
        n = round(PARK_N * share)
        pred = 1 - sex_mix(spec, {**NONE, "copd": True, "age": age}, PARK_MALE, 5)
        out.append(
            result_row(
                dataset,
                period,
                n,
                f"COPD aged {band}: predicted 5-year mortality",
                pred,
                notes,
                "park_2019",
            )
        )
        out.append(
            result_row(
                dataset,
                period,
                n,
                f"COPD aged {band}: observed 5-year mortality",
                mortality,
                notes,
                "park_2019",
            )
        )
    return out


def _life_expectancy(s, horizon: float = 60.0, step: float = 0.05) -> float:
    """Trapezoidal integral of S(t) over [0, horizon]."""
    n = round(horizon / step)
    return step * (sum(s(k * step) for k in range(1, n)) + 0.5 * (s(0.0) + s(horizon)))


def bhatt(spec) -> list[dict[str, Any]]:
    dataset = "NHLBI Pooled Cohorts, U.S. (Bhatt et al. JAMA Intern Med 2026)"
    period = "Enrolled 1983-2011, followed to 2020"
    notes = (
        "Published cohort: ADO layer at age 65 with a mid-grade FEV1 % predicted per GOLD stage"
        " (breathlessness averaged), as a ratio to the same model's population life expectancy;"
        " observed: published life expectancy at 65 by GOLD stage divided by that without COPD"
        " (the cohort is healthier than the U.S. population, so ratios are compared). n is the"
        " whole cohort; stage sizes are not given in the abstract."
    )
    table = load_life_table("us_2024")

    def population(t: float) -> float:
        return sum(
            w * math.exp(-population_cum_hazard(q, 65, t))
            for q, w in ((table.female, BHATT_FEMALE), (table.male, 1 - BHATT_FEMALE))
        )

    e_pop = _life_expectancy(population)
    out = []
    for stage, fev1 in GOLD_FEV1.items():
        e = 0.0
        for sex, w in (("female", BHATT_FEMALE), ("male", 1 - BHATT_FEMALE)):
            obs = {**NONE, "copd": True, "age": 65, "sex": sex, "fev1_pct": fev1}
            e += w * _life_expectancy(survival_function(spec, obs))
        out.append(
            result_row(
                dataset,
                period,
                BHATT_N,
                f"COPD {stage}: predicted life expectancy at 65 relative to no COPD",
                e / e_pop,
                notes,
                "bhatt_2026",
            )
        )
        out.append(
            result_row(
                dataset,
                period,
                BHATT_N,
                f"COPD {stage}: observed life expectancy at 65 relative to no COPD",
                BHATT[stage] / BHATT["none"],
                notes,
                "bhatt_2026",
            )
        )
    return out


def main() -> None:
    spec = build()
    results = [*nhanes(spec), *park(spec), *bhatt(spec)]
    OUT.write_text(json.dumps({"results": results}, indent=1) + "\n", "utf-8")
    for r in results:
        print(f"{r['n']:>7}  {r['metric']}: {r['value']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
