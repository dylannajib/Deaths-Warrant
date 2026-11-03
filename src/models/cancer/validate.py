"""Test the cancer model's accuracy on MSK-CHORD: real patients, testing only, never training.

Download the MSK-CHORD (Jee et al., Nature 2024; CC BY-NC-ND 4.0) clinical files from
https://github.com/cBioPortal/datahub/tree/master/public/msk_chord_2024 into the git-ignored
``data/msk_chord/``: data_clinical_patient.txt, data_clinical_sample.txt,
data_timeline_diagnosis.txt. Then, from src/backend:

    ../../.venv/bin/python ../models/cancer/validate.py

Writes ``validation.json`` beside this file, containing aggregate results only (every group has
n >= 20); patient-level data never leaves ``data/``.

Each patient is predicted as of their first MSK-IMPACT sequencing (day 0, the origin of
MSK-CHORD's overall survival), using only what a medical record would hold at that date:
age, sex, the tumour-registry primary site and SEER summary stage at diagnosis, and the years
since diagnosis. Two scenarios are reported:

* ``registry``: stage at diagnosis as recorded by the tumour registry;
* ``registry + metastatic sample``: additionally, a first sequenced sample taken from a
  metastasis is treated as a recorded distant metastasis dated day 0 (as a metastasis code in
  a FHIR record would be).

Assumptions (stated in the published notes): age at day 0 = CURRENT_AGE_DEID minus follow-up
(the dataset gives age at last contact or death; ages capped at 89 are excluded); patients with
more than one registry primary are excluded so the site is unambiguous.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections.abc import Iterator
from multiprocessing import Pool
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "backend")]  # model.py, deaths_warrant
from model import SITES, build  # noqa: E402

from deaths_warrant.evaluate import evaluate  # noqa: E402
from deaths_warrant.validation import calibration_at, harrell_c, kaplan_meier, km_median  # noqa: E402

DATA = HERE.parents[2] / "data" / "msk_chord"
OUT = HERE / "validation.json"
DATASET = "MSK-CHORD (Memorial Sloan Kettering, Jee et al. 2024)"
PERIOD = "MSK-IMPACT sequenced from 2014; outcomes to the 9 Sep 2023 data snapshot"
MIN_GROUP = 20
MIN_DEATHS = 20  # fewer deaths make the C-index too noisy to report
YEARS = (1, 3, 5)

STAGE = {
    "Localized": "localized",
    "Distant": "distant",
    "Distant metastases/systemic disease": "distant",
}
TOPOGRAPHY = re.compile(r"\(M(\d{4})/(\d) \| (C\d\d)\d?\)")
ICD10_TO_SITE = {p: key for key, (_, icd10, _) in SITES.items() for p in icd10}


def _rows(name: str) -> Iterator[dict[str, str]]:
    with open(DATA / name, encoding="utf-8") as f:
        yield from csv.DictReader((line for line in f if not line.startswith("#")), delimiter="\t")


def site_of(morphology: int, topography: str) -> str:
    """SEER site recode from ICD-O-3: histology-defined groups first, then topography."""
    if 9590 <= morphology <= 9729:
        return "hodgkin" if 9650 <= morphology <= 9667 else "nhl"
    if morphology in (9731, 9732, 9734):
        return "myeloma"
    if 9800 <= morphology <= 9948:
        return "leukaemia"
    if 9050 <= morphology <= 9055:
        return "mesothelioma"
    if 8720 <= morphology <= 8790 and topography == "C44":
        return "melanoma"
    return ICD10_TO_SITE.get(topography, "other")


def _stage(summary: str) -> str | None:
    s = summary.strip()
    return "regional" if s.startswith("Regional") else STAGE.get(s)


def cohort() -> list[dict[str, Any]]:
    primaries: dict[str, list[dict[str, str]]] = {}
    for r in _rows("data_timeline_diagnosis.txt"):
        if r["SUBTYPE"] == "Primary":
            primaries.setdefault(r["PATIENT_ID"], []).append(r)
    first_sample: dict[str, str] = {}
    for r in _rows("data_clinical_sample.txt"):
        pid, sid = r["PATIENT_ID"], r["SAMPLE_ID"]
        if pid not in first_sample or sid < first_sample[pid][0]:
            first_sample[pid] = (sid, r["SAMPLE_TYPE"])  # type: ignore[assignment]
    patients = []
    for p in _rows("data_clinical_patient.txt"):
        pid = p["PATIENT_ID"]
        dx = primaries.get(pid, [])
        m = TOPOGRAPHY.search(dx[0]["DX_DESCRIPTION"]) if len(dx) == 1 else None
        if (
            not m
            or m.group(2) != "3"  # invasive only
            or not p["OS_MONTHS"]
            or not p["CURRENT_AGE_DEID"]
            or p["GENDER"] not in ("Female", "Male")
        ):
            continue
        years = float(p["OS_MONTHS"]) / 12
        current_age = float(p["CURRENT_AGE_DEID"])
        since = -float(dx[0]["START_DATE"]) / 365.25
        age = current_age - years
        if current_age >= 89 or years <= 0 or since < 0 or age < 18:
            continue
        patients.append(
            {
                "years": years,
                "died": p["OS_STATUS"].startswith("1"),
                "observed": {
                    "age": age,
                    "sex": p["GENDER"].lower(),
                    "site": site_of(int(m.group(1)), m.group(3)),
                    "stage": _stage(dx[0]["SUMMARY"]),
                    "since": since,
                },
                "metastatic_sample": first_sample.get(pid, ("", ""))[1] == "Metastasis",
            }
        )
    return patients


def _scenario(patient: dict[str, Any], with_metastasis: bool) -> dict[str, Any]:
    observed = dict(patient["observed"])
    if with_metastasis and patient["metastatic_sample"]:
        observed.update(stage="distant", since=0.0)
    return observed


_SPEC = None


def predict(observed: dict[str, Any]) -> dict[str, Any]:
    global _SPEC
    if _SPEC is None:
        _SPEC = build()
    r = evaluate(_SPEC, observed)
    horizon = 60.0  # evaluator horizon: a median beyond it is reported as None
    return {
        "layer": r["layer"]["id"],
        "median": r["median_years"] if r["median_years"] is not None else horizon,
        "low": r["range_low_years"] if r["range_low_years"] is not None else horizon,
        "high": r["range_high_years"] if r["range_high_years"] is not None else horizon,
        "survival_at": r["survival_at"],
        "curve": [s for _, s in r["curve"]],
        "curve_step": r["curve"][1][0],
    }


def _row(base: dict[str, Any], metric: str, value: float, notes: str) -> dict[str, Any]:
    return {**base, "metric": metric, "value": round(value, 3), "notes": notes}


MSK_CHORD = {"dataset": DATASET, "period": PERIOD, "source": "msk_chord"}


def _base(meta: dict[str, str], n: int) -> dict[str, Any]:
    return {"dataset": meta["dataset"], "period": meta["period"], "n": n, "source": meta["source"]}


def metrics(
    name: str,
    group: list[tuple[dict[str, Any], dict[str, Any]]],
    notes: str,
    meta: dict[str, str] = MSK_CHORD,
    years: tuple[int, ...] = YEARS,
) -> list[dict]:
    if len(group) < MIN_GROUP:
        return []
    times = [p["years"] for p, _ in group]
    events = [p["died"] for p, _ in group]
    base = _base(meta, len(group))
    out = []
    if sum(events) >= MIN_DEATHS:
        c = harrell_c(times, events, [pred["median"] for _, pred in group])
        out.append(_row(base, f"{name}: Harrell's C-index", c, notes))
    for t in years:
        predicted, observed = calibration_at(
            t, times, events, [p["survival_at"][str(t)] for _, p in group]
        )
        out.append(_row(base, f"{name}: predicted {t}-year survival", predicted, notes))
        out.append(
            _row(base, f"{name}: observed {t}-year survival (Kaplan-Meier)", observed, notes)
        )
    # Cohort median: where the average predicted curve crosses 0.5, against Kaplan-Meier.
    step = group[0][1]["curve_step"]
    mean_curve = [
        sum(col) / len(group) for col in zip(*(p["curve"] for _, p in group), strict=True)
    ]
    crossing = next((k * step for k, s in enumerate(mean_curve) if s <= 0.5), None)
    km = km_median(kaplan_meier(times, events))
    if crossing is not None:
        out.append(_row(base, f"{name}: predicted median survival (years)", crossing, notes))
    if km is not None:
        out.append(_row(base, f"{name}: observed median survival (years, Kaplan-Meier)", km, notes))
    return out


def years_lived(
    group: list[tuple[dict[str, Any], dict[str, Any]]],
    notes: str,
    meta: dict[str, str] = MSK_CHORD,
) -> list[dict]:
    """Prediction against actual years lived, for patients whose death was observed.

    Restricting to deaths favours short survivors (long survivors are still alive, censored),
    so these figures complement, and do not replace, the censoring-aware metrics above.
    """
    dead = [(p, pred) for p, pred in group if p["died"]]
    base = _base(meta, len(dead))
    errors = sorted(abs(pred["median"] - p["years"]) for p, pred in dead)
    within = sum(pred["low"] <= p["years"] <= pred["high"] for p, pred in dead) / len(dead)
    note = notes + " Deceased patients only, so biased towards short survival."
    return [
        _row(
            base,
            "Deceased: median absolute error, predicted median vs years lived (years)",
            errors[len(errors) // 2],
            note,
        ),
        _row(
            base,
            "Deceased: share whose years lived fell in the predicted 25-75% range",
            within,
            note,
        ),
    ]


def main() -> None:
    patients = cohort()
    results: list[dict[str, Any]] = []
    summary = {}
    with Pool() as pool:
        for label, with_met in (("registry", False), ("registry + metastatic sample", True)):
            preds = pool.map(predict, [_scenario(p, with_met) for p in patients], chunksize=200)
            pairs = list(zip(patients, preds, strict=True))
            notes = (
                "Predicted at first sequencing from age, sex, registry site and stage at"
                " diagnosis, and years since diagnosis"
                + (
                    "; a metastatic first sample counts as distant stage from day 0."
                    if with_met
                    else "."
                )
            )
            results += metrics(f"All patients ({label})", pairs, notes)
            if with_met:
                results += years_lived(pairs, notes)
            for layer in ("site_stage", "site", "all_sites"):
                results += metrics(
                    f"Layer {layer} ({label})", [x for x in pairs if x[1]["layer"] == layer], notes
                )
            if with_met:
                for stage in ("localized", "regional", "distant"):
                    group = [x for x in pairs if _scenario(x[0], True)["stage"] == stage]
                    results += metrics(f"Stage {stage} ({label})", group, notes)
                sites: dict[str, list] = {}
                for x in pairs:
                    sites.setdefault(x[0]["observed"]["site"], []).append(x)
                for site, group in sorted(sites.items(), key=lambda kv: -len(kv[1]))[:6]:
                    results += metrics(f"Site {site} ({label})", group, notes)
            summary[label] = len(pairs)
    OUT.write_text(json.dumps({"cohort": summary, "results": results}, indent=1) + "\n", "utf-8")
    for r in results:
        print(f"{r['n']:>6}  {r['metric']}: {r['value']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
