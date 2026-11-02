"""Test the cardiovascular model's accuracy on real patients (testing only, never training).

No open patient-level heart-failure or cardiovascular data with outcomes from 2020 onwards
exists (all such datasets need credentialed access), so two kinds of evidence are used:

1. Patient level: the UCI "heart failure clinical records" (Ahmad et al. 2017; 299 patients,
   2015; CC BY 4.0). Download heart_failure_clinical_records_dataset.csv from
   https://archive.ics.uci.edu/dataset/519/heart+failure+clinical+records into the
   git-ignored ``data/uci_hf/``.
2. Published cohort results: the model's prediction for a cohort's published age and sex mix,
   against the cohort's published observed survival (figures quoted below with their source).

From src/backend:  ../../.venv/bin/python ../models/cardiovascular/validate.py
Writes ``validation.json`` beside this file (aggregate results only, every group n >= 20).
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "backend")]  # model.py, deaths_warrant
from model import CONDITIONS, build  # noqa: E402

from deaths_warrant.evaluate import evaluate  # noqa: E402
from deaths_warrant.validation import calibration_at, harrell_c  # noqa: E402

UCI = HERE.parents[2] / "data" / "uci_hf" / "heart_failure_clinical_records_dataset.csv"
OUT = HERE / "validation.json"
NO_CONDITIONS = {key: False for key in CONDITIONS} | {"diabetes": False, "copd": False}

# Taylor et al. BMJ 2019, Tables 1 and 3: UK CPRD incident heart failure 2000-2017.
TAYLOR = [  # (age band, representative age, n, observed 1-year, observed 5-year survival)
    ("45-54", 50, 1938, 0.903, 0.785),
    ("55-64", 60, 5426, 0.879, 0.706),
    ("65-74", 70, 12485, 0.835, 0.591),
    ("75-84", 80, 21534, 0.765, 0.432),
    ("85-94", 90, 13453, 0.632, 0.223),
    ("95+", 97, 1123, 0.439, 0.060),
]
TAYLOR_MALE = 0.522
# Peng et al. Stroke 2022: first acute stroke, Australia and New Zealand 2008-2017.
PENG = {
    "n": 313_162,
    "age_mean": 73.0,
    "age_sd": 14.6,
    "male": 0.520,
    "observed": {"1": 0.730, "5": 0.528, "10": 0.364},
}
# Brazilian MAGGIC validation (Arq Bras Cardiol 2026): HF outpatients enrolled 2008-2014.
BRAZIL = {"n": 866, "observed_3y_mortality": 0.334, "maggic_predicted_3y_mortality": 0.209}


def _row(dataset: str, period: str, n: int, metric: str, value: float, notes: str, source: str):
    return {
        "dataset": dataset,
        "period": period,
        "n": n,
        "metric": metric,
        "value": round(value, 3),
        "notes": notes,
        "source": source,
    }


def _survival(result: dict[str, Any], t: float) -> float:
    """S(t) from the evaluator's 0.25-year curve (exact at the curve's grid points)."""
    step = result["curve"][1][0]
    return result["curve"][round(t / step)][1]


def _sex_mix(spec, observed: dict[str, Any], male: float, t: float) -> float:
    return sum(
        w * _survival(evaluate(spec, {**observed, "sex": sex}), t)
        for sex, w in (("male", male), ("female", 1 - male))
    )


def uci(spec) -> list[dict[str, Any]]:
    if not UCI.exists():
        raise SystemExit(f"missing {UCI}; see this module's docstring")
    with open(UCI, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    times, events, medians, half_year = [], [], [], []
    for r in rows:
        # What a record would hold: no NYHA, blood pressure, BMI, HF duration or medication list.
        observed = {
            **NO_CONDITIONS,
            "heart_failure": True,
            "age": float(r["age"]),
            "sex": "male" if r["sex"] == "1" else "female",
            "ef": float(r["ejection_fraction"]),
            "creatinine": float(r["serum_creatinine"]) * 88.4,
            "smoker": "current" if r["smoking"] == "1" else "not_current",
            "diabetes": r["diabetes"] == "1",
        }
        result = evaluate(spec, observed)
        times.append(float(r["time"]) / 365.25)
        events.append(r["DEATH_EVENT"] == "1")
        medians.append(result["median_years"] if result["median_years"] is not None else 60.0)
        half_year.append(_survival(result, 0.5))
    dataset = "UCI heart failure clinical records (Faisalabad, Pakistan; Ahmad et al. 2017)"
    period = "April-December 2015 (follow-up up to 285 days)"
    notes = (
        "Patient-level, predicted at enrolment from age, sex, ejection fraction, creatinine,"
        " smoking and diabetes (MAGGIC layer; other inputs averaged). Pre-2020: the only open"
        " patient-level heart-failure survival data found."
    )
    predicted, observed_km = calibration_at(0.5, times, events, half_year)
    return [
        _row(
            dataset,
            period,
            len(rows),
            "Heart failure, MAGGIC layer: Harrell's C-index",
            harrell_c(times, events, medians),
            notes,
            "uci_hf_2015",
        ),
        _row(
            dataset,
            period,
            len(rows),
            "Heart failure, MAGGIC layer: predicted 6-month survival",
            predicted,
            notes,
            "uci_hf_2015",
        ),
        _row(
            dataset,
            period,
            len(rows),
            "Heart failure, MAGGIC layer: observed 6-month survival (Kaplan-Meier)",
            observed_km,
            notes,
            "uci_hf_2015",
        ),
    ]


def taylor(spec) -> list[dict[str, Any]]:
    dataset = "UK CPRD incident heart failure (Taylor et al. BMJ 2019)"
    period = "Diagnosed 2000-2017"
    notes = (
        "Reproduction check, not independent validation: the heart-failure layer (no ejection"
        " fraction) is built from this cohort's published survival. Predicted at diagnosis at"
        " the age band's representative age with the cohort's sex mix."
    )
    out = []
    for band, age, n, s1, s5 in TAYLOR:
        observed = {**NO_CONDITIONS, "heart_failure": True, "age": age, "hf_years": 0.0}
        for t, obs in ((1, s1), (5, s5)):
            pred = _sex_mix(spec, observed, TAYLOR_MALE, t)
            out.append(
                _row(
                    dataset,
                    period,
                    n,
                    f"Heart failure aged {band}: predicted {t}-year survival",
                    pred,
                    notes,
                    "taylor_2019",
                )
            )
            out.append(
                _row(
                    dataset,
                    period,
                    n,
                    f"Heart failure aged {band}: observed {t}-year survival",
                    obs,
                    notes,
                    "taylor_2019",
                )
            )
    return out


def peng(spec) -> list[dict[str, Any]]:
    dataset = "Australia and New Zealand first acute stroke (Peng et al. Stroke 2022)"
    period = "First stroke 2008-2017"
    notes = (
        "Published cohort: base layer, stroke only, averaged over a normal age distribution"
        " with the published mean and SD (ages 18-100) and the cohort's sex mix. The stroke"
        " hazard ratio describes people with a history of stroke, so early deaths after an"
        " acute stroke are expected to be underpredicted."
    )
    ages = range(18, 101)
    density = [math.exp(-0.5 * ((a - PENG["age_mean"]) / PENG["age_sd"]) ** 2) for a in ages]
    total = sum(density)
    out = []
    for t_key, obs in PENG["observed"].items():
        t = float(t_key)
        pred = sum(
            d / total * _sex_mix(spec, {**NO_CONDITIONS, "stroke": True, "age": a}, PENG["male"], t)
            for a, d in zip(ages, density, strict=True)
        )
        out.append(
            _row(
                dataset,
                period,
                PENG["n"],
                f"Stroke: predicted {t_key}-year survival",
                pred,
                notes,
                "peng_2022",
            )
        )
        out.append(
            _row(
                dataset,
                period,
                PENG["n"],
                f"Stroke: observed {t_key}-year survival",
                obs,
                notes,
                "peng_2022",
            )
        )
    return out


def brazil() -> list[dict[str, Any]]:
    dataset = "Brazilian heart failure outpatients, Porto Alegre (Arq Bras Cardiol 2026)"
    period = "Enrolled 2008-2014, 3-year follow-up"
    notes = (
        "Published external validation of the MAGGIC score that this model's heart-failure"
        " layer reproduces at 1 and 3 years: MAGGIC underpredicted 3-year mortality here."
    )
    return [
        _row(
            dataset,
            period,
            BRAZIL["n"],
            "Heart failure: MAGGIC-predicted 3-year mortality (published)",
            BRAZIL["maggic_predicted_3y_mortality"],
            notes,
            "vargas_2026",
        ),
        _row(
            dataset,
            period,
            BRAZIL["n"],
            "Heart failure: observed 3-year mortality (published)",
            BRAZIL["observed_3y_mortality"],
            notes,
            "vargas_2026",
        ),
    ]


def main() -> None:
    spec = build()
    results = [*uci(spec), *taylor(spec), *peng(spec), *brazil()]
    OUT.write_text(json.dumps({"results": results}, indent=1) + "\n", "utf-8")
    for r in results:
        print(f"{r['n']:>7}  {r['metric']}: {r['value']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
