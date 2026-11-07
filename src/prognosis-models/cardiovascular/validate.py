"""Test the cardiovascular model's accuracy on real patients (testing only, never training).

Open patient-level cardiovascular data is scarce (most datasets need credentialed access), so
three kinds of evidence are used, each labelled with its period:

1. Patient level: the UCI "heart failure clinical records" (Ahmad et al. 2017, 299 patients,
   2015, CC BY 4.0). Download heart_failure_clinical_records_dataset.csv from
   https://archive.ics.uci.edu/dataset/519/heart+failure+clinical+records into the
   git-ignored ``data/uci_hf/``.
2. Patient level: the Czech FAR NHL registry (Spinar et al. PLoS One 2019, 1,088 patients with
   ejection fraction < 50%, enrolled 2014-2015, followed to 2017, CC BY 4.0). Download S1 Table
   from https://journals.plos.org/plosone/article/file?type=supplementary&id=10.1371/journal.pone.0214363.s001
   as ``data/far_nhl/pone.0214363.s001.csv``.
3. Published cohort results: the model's prediction for a cohort's published age and sex mix,
   against the cohort's published observed survival (figures quoted below with their source).

From src/backend:  ../../.venv/bin/python ../prognosis-models/cardiovascular/validate.py
Writes ``validation.json`` beside this file (aggregate results only, every group n >= 20).
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "backend")]  # model.py, general
from model import CONDITIONS, ROMAN, build  # noqa: E402

from general.evaluate import evaluate  # noqa: E402
from general.validation import (  # noqa: E402
    calibration_at,
    curve_at,
    harrell_c,
    result_row,
    sex_mix,
    write_results,
)

UCI = HERE.parents[2] / "data" / "uci_hf" / "heart_failure_clinical_records_dataset.csv"
FAR_NHL = HERE.parents[2] / "data" / "far_nhl" / "pone.0214363.s001.csv"
OUT = HERE / "validation.json"
NO_CONDITIONS = {key: False for key in CONDITIONS} | {"diabetes": False, "copd": False}

# Peng et al. Stroke 2022: first acute stroke, Australia and New Zealand 2008-2017.
PENG = {
    "n": 313_162,
    "age_mean": 73.0,
    "age_sd": 14.6,
    "male": 0.520,
    "observed": {"1": 0.730, "5": 0.528, "10": 0.364},
}
# Bray et al. Lancet Public Health 2018: first-ever stroke, England (SSNAP) Jul 2013-Mar 2016.
BRAY = {
    "n": 107_891,  # patients with more than 365 days of follow-up (Table 1)
    "quartiles": [18, 66, 77, 85, 100],  # age: median 77, IQR 66-85 (ends assumed)
    "male": 72_912 / 145_324,
    "observed_1y": 1 - 28_434 / 107_891,
}
# Brazilian MAGGIC validation (Arq Bras Cardiol 2026): HF outpatients enrolled 2008-2014.
BRAZIL = {"n": 866, "observed_3y_mortality": 0.334, "maggic_predicted_3y_mortality": 0.209}


def uci(spec) -> list[dict[str, Any]]:
    if not UCI.exists():
        raise SystemExit(f"missing {UCI}; see this module's docstring")
    with open(UCI, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    dataset = "UCI heart failure clinical records (Faisalabad, Pakistan, Ahmad et al. 2017)"
    period = "April-December 2015 (follow-up up to 285 days)"
    times = [float(r["time"]) / 365.25 for r in rows]
    events = [r["DEATH_EVENT"] == "1" for r in rows]
    out = []
    # Every patient was hospitalised for heart failure at enrolment. Scenario 1: the record does
    # not show that stay (other inputs averaged over the MAGGIC cohort). Scenario 2: it does,
    # so the recent-admission layer applies.
    for admitted, layer in ((False, "MAGGIC layer"), (True, "MAGGIC after a recent admission")):
        medians, half_year = [], []
        for r in rows:
            # What a record would hold: no NYHA, blood pressure, BMI, HF duration or medicines.
            observed = {
                **NO_CONDITIONS,
                "heart_failure": True,
                "hf_admission": admitted,
                "age": float(r["age"]),
                "sex": "male" if r["sex"] == "1" else "female",
                "ef": float(r["ejection_fraction"]),
                "creatinine": float(r["serum_creatinine"]) * 88.4,
                "smoker": "current" if r["smoking"] == "1" else "not_current",
                "diabetes": r["diabetes"] == "1",
            }
            result = evaluate(spec, observed)
            medians.append(result["median_years"] if result["median_years"] is not None else 60.0)
            half_year.append(curve_at(result, 0.5))
        notes = (
            "Patient-level, predicted at enrolment from age, sex, ejection fraction, creatinine,"
            " smoking and diabetes; other inputs averaged."
            + (
                " Assumes the record shows the heart-failure hospital stay, so an unrecorded"
                " NYHA class is taken as IV."
                if admitted
                else " Assumes the record does not show the hospital stay."
            )
        )
        meta = {"dataset": dataset, "period": period, "notes": notes, "source": "uci_hf_2015"}
        predicted, observed_km = calibration_at(0.5, times, events, half_year)
        out += [
            result_row(
                meta,
                len(rows),
                f"Heart failure, {layer}: Harrell's C-index",
                harrell_c(times, events, medians),
            ),
            result_row(
                meta, len(rows), f"Heart failure, {layer}: predicted 6-month survival", predicted
            ),
            result_row(
                meta,
                len(rows),
                f"Heart failure, {layer}: observed 6-month survival (Kaplan-Meier)",
                observed_km,
            ),
        ]
    return out


def _auc(scores: list[float], events: list[bool]) -> float:
    """Concordance of predicted survival with a binary outcome (higher survival, no event)."""
    pos = [x for x, e in zip(scores, events, strict=True) if e]
    neg = [x for x, e in zip(scores, events, strict=True) if not e]
    wins = sum((n > p) + 0.5 * (n == p) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def far_nhl(spec) -> list[dict[str, Any]]:
    if not FAR_NHL.exists():
        raise SystemExit(f"missing {FAR_NHL}; see this module's docstring")
    with open(FAR_NHL, encoding="utf-8-sig") as f:
        rows = [
            r
            for r in csv.DictReader(f, delimiter=";")
            if all(r[k].strip() for k in ("ejection_fraction_percent", "lab_creatinine", "BMI"))
        ]
    num = lambda r, k: float(r[k].replace(",", "."))  # noqa: E731 - Czech decimal commas
    events = [r["endpoint_2years"] == "1" for r in rows]
    dataset = "FAR NHL registry, Czech Republic (Spinar et al. PLoS One 2019)"
    period = "Enrolled Nov 2014-Nov 2015, followed to Nov 2017"
    out = []
    for with_nyha in (True, False):
        two_year = []
        for r in rows:
            observed = {
                **NO_CONDITIONS,
                "heart_failure": True,
                "age": num(r, "age_at_admission"),
                "sex": "male" if r["sex"] == "Man" else "female",
                "ef": num(r, "ejection_fraction_percent"),
                "sbp": num(r, "systolic_blood_pressure"),
                "bmi": num(r, "BMI"),
                "creatinine": num(r, "lab_creatinine"),
                "smoker": "current" if r["anamnesis_smoking"] == "Smoker" else "not_current",
                "diabetes": r["anamnesis_DM"] == "1",
                "copd": r["anamnesis_COPD"] == "1",
                "beta_blocker": r["medication_betablockers"] == "1",
                "acei_arb": r["medication_ACEI_ARB"] == "1",
            }
            if r["years_since_diagnosis_of_heart_failure"].strip():  # 5 blank: averaged
                observed["hf_years"] = num(r, "years_since_diagnosis_of_heart_failure")
            if not with_nyha:
                two_year.append(curve_at(evaluate(spec, observed), 2))
                continue
            # Half classes (e.g. 2.5) are averaged over the two neighbouring classes.
            nyha = num(r, "NYHA")
            classes = {ROMAN[math.floor(nyha) - 1], ROMAN[math.ceil(nyha) - 1]}
            two_year.append(
                sum(curve_at(evaluate(spec, {**observed, "nyha": c}), 2) for c in classes)
                / len(classes)
            )
        layer = "all MAGGIC inputs" if with_nyha else "NYHA class not recorded"
        notes = (
            "Patient-level, outpatients with ejection fraction < 50% (MAGGIC layer)."
            + (
                " Every MAGGIC input taken from the registry."
                if with_nyha
                else " As if the record lacked NYHA class (averaged over the MAGGIC cohort)."
            )
            + " The registry's 2-year outcome is death, heart transplant or LVAD (combined);"
            " its date is not given, so only 2-year survival can be compared."
        )
        meta = {"dataset": dataset, "period": period, "notes": notes, "source": "far_nhl_2019"}
        out += [
            result_row(
                meta,
                len(rows),
                f"Heart failure, {layer}: C-index (2-year outcome)",
                _auc(two_year, events),
            ),
            result_row(
                meta,
                len(rows),
                f"Heart failure, {layer}: predicted 2-year survival",
                sum(two_year) / len(rows),
            ),
            result_row(
                meta,
                len(rows),
                f"Heart failure, {layer}: observed 2-year survival without transplant or LVAD",
                1 - sum(events) / len(rows),
            ),
        ]
    return out


def _stroke_survival(spec, ages: list[tuple[float, float]], male: float, t: float) -> float:
    """Cohort survival t years after a first stroke, averaged over (age, weight) pairs."""
    total = sum(w for _, w in ages)
    return sum(
        w
        / total
        * sex_mix(spec, {**NO_CONDITIONS, "stroke": True, "stroke_years": 0.0, "age": a}, male, t)
        for a, w in ages
    )


def peng(spec) -> list[dict[str, Any]]:
    dataset = "Australia and New Zealand first acute stroke (Peng et al. Stroke 2022)"
    period = "First stroke 2008-2017"
    notes = (
        "Published cohort, independent of the stroke layer's sources: predicted at the stroke"
        " (stroke layer), averaged over a normal age distribution with the published mean and"
        " SD (ages 18-100) and the cohort's sex mix."
    )
    meta = {"dataset": dataset, "period": period, "notes": notes, "source": "peng_2022"}
    ages = [
        (a, math.exp(-0.5 * ((a - PENG["age_mean"]) / PENG["age_sd"]) ** 2)) for a in range(18, 101)
    ]
    out = []
    for t_key, obs in PENG["observed"].items():
        pred = _stroke_survival(spec, ages, PENG["male"], float(t_key))
        out.append(result_row(meta, PENG["n"], f"Stroke: predicted {t_key}-year survival", pred))
        out.append(result_row(meta, PENG["n"], f"Stroke: observed {t_key}-year survival", obs))
    return out


def bray(spec) -> list[dict[str, Any]]:
    dataset = "England first-ever stroke, SSNAP national register (Bray et al. 2018)"
    period = "Admitted Jul 2013-Mar 2016, 1-year follow-up"
    notes = (
        "Published cohort, independent of the stroke layer's sources: predicted at admission"
        " (stroke layer), with ages spread evenly within each published quartile (median 77,"
        " IQR 66-85; ends 18 and 100 assumed) and the cohort's sex mix. Observed: 1-year"
        " all-cause mortality among patients with more than a year of follow-up."
    )
    meta = {"dataset": dataset, "period": period, "notes": notes, "source": "bray_2018"}
    q = BRAY["quartiles"]
    ages = [
        (a + 0.5, 0.25 / (hi - lo)) for lo, hi in zip(q, q[1:], strict=False) for a in range(lo, hi)
    ]
    pred = _stroke_survival(spec, ages, BRAY["male"], 1.0)
    return [
        result_row(meta, BRAY["n"], "Stroke: predicted 1-year survival", pred),
        result_row(meta, BRAY["n"], "Stroke: observed 1-year survival", BRAY["observed_1y"]),
    ]


def brazil() -> list[dict[str, Any]]:
    dataset = "Brazilian heart failure outpatients, Porto Alegre (Arq Bras Cardiol 2026)"
    period = "Enrolled 2008-2014, 3-year follow-up"
    notes = (
        "Published external validation of the MAGGIC score that this model's heart-failure"
        " layer reproduces at 1 and 3 years: MAGGIC underpredicted 3-year mortality here."
    )
    meta = {"dataset": dataset, "period": period, "notes": notes, "source": "vargas_2026"}
    return [
        result_row(
            meta,
            BRAZIL["n"],
            "Heart failure: MAGGIC-predicted 3-year mortality (published)",
            BRAZIL["maggic_predicted_3y_mortality"],
        ),
        result_row(
            meta,
            BRAZIL["n"],
            "Heart failure: observed 3-year mortality (published)",
            BRAZIL["observed_3y_mortality"],
        ),
    ]


def main() -> None:
    spec = build()
    results = [*uci(spec), *far_nhl(spec), *peng(spec), *bray(spec), *brazil()]
    write_results(OUT, results)


if __name__ == "__main__":
    main()
