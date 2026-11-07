"""Test the cancer model on TCGA patients diagnosed 2010 onwards (testing only, never training).

The Cancer Genome Atlas clinical data as harmonised by the NCI Genomic Data Commons, served by
the public cBioPortal API (studies ``*_tcga_gdc``, open access, no login). From src/backend:

    ../../.venv/bin/python ../prognosis-models/cancer/validate_tcga.py

Downloads each study's patient table into the git-ignored ``data/tcga_gdc/`` once, then writes
``validation_tcga.json`` beside this file (aggregate results only, every group n >= 20).

Each patient is predicted at diagnosis (TCGA overall survival starts there) from age at
diagnosis, sex, the ICD-O-3 site and morphology, and a summary stage derived from the
pathological TNM stage:

* distant: M1 (any subcategory) or overall stage IV.
* regional: N1-N3, or N0 with overall stage III (tumour extension).
* localized: N0 with overall stage I-II.
* otherwise unknown, so the model averages over the published stage mix.

AJCC pathological stage is not the SEER summary stage the model was built on, so this mapping
is an approximation (stated in the notes). Patients with a prior malignancy, a diagnosis before
2010, or no survival time are excluded. TCGA does not overlap with MSK-CHORD.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from multiprocessing import Pool
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "backend")]  # validate.py, general
from validate import metrics, predict, site_of, subgroups, years_lived  # noqa: E402

from general.validation import write_results  # noqa: E402

DATA = HERE.parents[2] / "data" / "tcga_gdc"
OUT = HERE / "validation_tcga.json"
API = "https://www.cbioportal.org/api"
FIRST_YEAR = 2010
META = {
    "dataset": "TCGA, harmonised by the NCI Genomic Data Commons (cBioPortal *_tcga_gdc)",
    "period": f"Diagnosed {FIRST_YEAR}-2013, followed from diagnosis",
    "source": "tcga_gdc",
}
ICD10 = re.compile(r"^(C\d\d)")
MORPHOLOGY = re.compile(r"^(\d{4})/(\d)")


def _get(url: str) -> Any:
    if not url.startswith(API):
        raise ValueError(f"refusing {url}")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - fixed https API
        return json.load(response)


def download() -> dict[str, dict[str, dict[str, str]]]:
    """study id -> patient id -> clinical attribute -> value (cached in data/tcga_gdc/)."""
    DATA.mkdir(parents=True, exist_ok=True)
    index = DATA / "studies.json"
    if not index.exists():
        studies = _get(f"{API}/studies?keyword=tcga_gdc&projection=SUMMARY")
        index.write_text(json.dumps(sorted(s["studyId"] for s in studies)), "utf-8")
    out = {}
    for study in json.loads(index.read_text("utf-8")):
        path = DATA / f"{study}.json"
        if not path.exists():
            rows = _get(
                f"{API}/studies/{study}/clinical-data?clinicalDataType=PATIENT"
                "&projection=SUMMARY&pageSize=10000000"
            )
            path.write_text(json.dumps(rows), "utf-8")
        patients: dict[str, dict[str, str]] = {}
        for r in json.loads(path.read_text("utf-8")):
            patients.setdefault(r["patientId"], {})[r["clinicalAttributeId"]] = r["value"]
        out[study] = patients
    return out


def _stage(p: dict[str, str]) -> str | None:
    overall = p.get("PATH_STAGE", "").removeprefix("Stage ").rstrip("ABC")
    m, n = p.get("PATH_M_STAGE", ""), p.get("PATH_N_STAGE", "")
    if m.startswith("M1") or overall == "IV":
        return "distant"
    if re.match(r"N[1-3]", n):
        return "regional"
    if n.startswith("N0"):
        return {"I": "localized", "II": "localized", "III": "regional"}.get(overall)
    return None


def cohort(studies: dict[str, dict[str, dict[str, str]]]) -> list[dict[str, Any]]:
    patients = []
    for patients_by_id in studies.values():
        for p in patients_by_id.values():
            topography = ICD10.match(p.get("ICD_10", ""))
            morphology = MORPHOLOGY.match(p.get("MORPHOLOGY", ""))
            year = p.get("YEAR_OF_DIAGNOSIS", "")
            if (
                not topography
                or not morphology
                or morphology.group(2) != "3"  # invasive only
                or not year.isdigit()
                or int(year) < FIRST_YEAR
                or p.get("PRIOR_MALIGNANCY") == "True"
                or not p.get("OS_MONTHS")
                or not p.get("AGE")
                or p.get("SEX") not in ("Female", "Male")
            ):
                continue
            years, age = float(p["OS_MONTHS"]) / 12, float(p["AGE"])
            if years <= 0 or age < 18:
                continue
            patients.append(
                {
                    "years": years,
                    "died": p["OS_STATUS"].startswith("1"),
                    "observed": {
                        "age": age,
                        "sex": p["SEX"].lower(),
                        "site": site_of(int(morphology.group(1)), topography.group(1)),
                        "stage": _stage(p),
                        "since": 0.0,
                    },
                }
            )
    return patients


def main() -> None:
    patients = cohort(download())
    with Pool() as pool:
        preds = pool.map(predict, [p["observed"] for p in patients], chunksize=100)
    pairs = list(zip(patients, preds, strict=True))
    notes = (
        "Predicted at diagnosis from age, sex, site and a summary stage derived from"
        " pathological TNM (an approximation of SEER summary stage). Follow-up is short"
        " (median about 2 years), so 5-year figures rest on few patients still at risk."
    )
    results = metrics("All patients", pairs, notes, META) + years_lived(pairs, notes, META)
    results += subgroups(
        pairs, notes, meta=META, stage_of=lambda p: p["observed"]["stage"], top_sites=8
    )
    cohort_summary = {"patients": len(pairs), "deaths": sum(p["died"] for p in patients)}
    write_results(OUT, results, cohort=cohort_summary)


if __name__ == "__main__":
    main()
