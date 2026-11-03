"""Download the MIMIC-IV FHIR demo and split it into one FHIR Bundle per patient.

python -m deaths_warrant.sources.mimic_fhir_demo

Source: Bennett A, et al. MIMIC-IV Clinical Database Demo on FHIR (version 2.1.0). PhysioNet.
https://physionet.org/content/mimic-iv-fhir-demo/2.1.0/ - open access, ODbL v1.0. 100 real,
de-identified patients (dates shifted into the 2100s). Files are verified against the
published SHA-256 sums and kept in the git-ignored data/mimic_fhir_demo/. The bundles feed the
end-to-end tests in src/frontend/src/e2e/. Used for testing only.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

from . import REPO, fetch

BASE = "https://physionet.org/files/mimic-iv-fhir-demo/2.1.0/"
OUT = REPO / "data" / "mimic_fhir_demo"
FILES = [
    "MimicPatient", "MimicCondition", "MimicEncounter", "MimicEncounterED", "MimicEncounterICU",
    "MimicMedication", "MimicMedicationRequest", "MimicObservationLabevents",
    "MimicObservationVitalSignsED", "MimicProcedure",
]  # fmt: skip


def _download() -> list[Path]:
    sums = dict(
        reversed(line.split()) for line in fetch(BASE + "SHA256SUMS.txt", "mimic/SHA256SUMS.txt")
        .read_text(encoding="utf-8").splitlines() if line.strip()
    )  # fmt: skip
    paths = []
    for name in FILES:
        rel = f"fhir/{name}.ndjson.gz"
        path = fetch(BASE + rel, f"mimic/{name}.ndjson.gz")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sums[rel]:
            raise RuntimeError(f"checksum mismatch for {rel}; delete {path} and retry")
        paths.append(path)
    return paths


def main() -> None:
    patients: dict[str, dict] = {}
    medications: dict[str, dict] = {}
    by_patient: dict[str, list[dict]] = {}
    for path in _download():
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                kind = r["resourceType"]
                if kind == "Patient":
                    patients[r["id"]] = r
                elif kind == "Medication":
                    medications[r["id"]] = r
                else:
                    ref = (r.get("subject") or r.get("patient") or {}).get("reference", "")
                    if ref.startswith("Patient/"):
                        by_patient.setdefault(ref.removeprefix("Patient/"), []).append(r)
    bundles = OUT / "bundles"
    bundles.mkdir(parents=True, exist_ok=True)
    for pid, patient in patients.items():
        if not re.fullmatch(r"[A-Za-z0-9-]+", pid):  # the id becomes a file name
            raise ValueError(f"unexpected patient id {pid!r}")
        resources = by_patient.get(pid, [])
        med_ids = {
            r.get("medicationReference", {}).get("reference", "").removeprefix("Medication/")
            for r in resources
            if r["resourceType"] == "MedicationRequest"
        }
        entries = [
            patient,
            *resources,
            *(medications[m] for m in sorted(med_ids) if m in medications),
        ]
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"fullUrl": f"{e['resourceType']}/{e['id']}", "resource": e} for e in entries
            ],
        }
        (bundles / f"{pid}.json").write_text(json.dumps(bundle), encoding="utf-8")
    print(f"wrote {len(patients)} bundles to {bundles}")


if __name__ == "__main__":
    main()
