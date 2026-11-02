"""Expand a model's SNOMED CT root concepts into explicit code lists.

python -m deaths_warrant.sources.snomed <model-id>

Reads ``src/models/<id>/snomed_roots.json`` (``{name: {"include": [...], "exclude": [...]}}``)
and writes ``snomed_sets.json``: every descendant-or-self of the included concepts, minus the
descendants-or-self of the excluded ones. The browser matches SNOMED codes exactly (it has no
terminology server), so hierarchies are flattened here, offline, via the public HL7 FHIR
terminology server. Only concept ids are stored, no SNOMED descriptions.
"""

from __future__ import annotations

import datetime
import json
import sys
import urllib.request
from typing import Any

from ..registry import MODELS_DIR
from . import USER_AGENT

SERVER = "https://tx.fhir.org/r4"
MAX_CODES = 5000


def descendants(root: str) -> tuple[set[str], str]:
    """Descendant-or-self codes of ``root`` and the SNOMED CT edition version used."""
    body = {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "count", "valueInteger": MAX_CODES},
            {
                "name": "valueSet",
                "resource": {
                    "resourceType": "ValueSet",
                    "compose": {
                        "include": [
                            {
                                "system": "http://snomed.info/sct",
                                "filter": [{"property": "concept", "op": "is-a", "value": root}],
                            }
                        ]
                    },
                },
            },
        ],
    }
    request = urllib.request.Request(  # noqa: S310 - fixed https server
        f"{SERVER}/ValueSet/$expand",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - fixed https
        expansion: dict[str, Any] = json.load(response)["expansion"]
    codes = {c["code"] for c in expansion.get("contains", [])}
    if expansion.get("total", len(codes)) != len(codes) or root not in codes:
        raise RuntimeError(f"incomplete expansion of {root}")
    version = next(
        (p.get("valueUri", "") for p in expansion.get("parameter", []) if p["name"] == "version"),
        "",
    )
    return codes, version


def main(model_id: str) -> None:
    folder = MODELS_DIR / model_id
    roots: dict[str, dict[str, list[str]]] = json.loads(
        (folder / "snomed_roots.json").read_text(encoding="utf-8")
    )
    cache: dict[str, set[str]] = {}
    versions: set[str] = set()

    def expand(root: str) -> set[str]:
        if root not in cache:
            cache[root], version = descendants(root)
            versions.add(version)
        return cache[root]

    sets = {}
    for name, spec in roots.items():
        codes = set().union(*(expand(r) for r in spec["include"]))
        codes -= set().union(*(expand(r) for r in spec.get("exclude", [])))
        sets[name] = sorted(codes, key=int)
        print(f"{name}: {len(codes)}")
    out = {
        "source": "snomed_ct",
        "server": SERVER,
        "editions": sorted(versions),
        "retrieved": datetime.date.today().isoformat(),
        "sets": sets,
    }
    (folder / "snomed_sets.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {folder / 'snomed_sets.json'}")


if __name__ == "__main__":
    main(sys.argv[1])
