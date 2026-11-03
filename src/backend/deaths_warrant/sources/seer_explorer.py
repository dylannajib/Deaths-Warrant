"""Fetch SEER relative survival into ``src/models/cancer/seer_relative_survival.json``.

python -m deaths_warrant.sources.seer_explorer [--refresh]

Source: SEER*Explorer, Surveillance Research Program, National Cancer Institute
(https://seer.cancer.gov/statistics-network/explorer/), SEER 21 registries. Published aggregate
statistics, a U.S. Government work, cited as NCI requests. For each site and age group at
diagnosis it stores, per SEER summary stage:

* ``curve``: relative survival at 1..10 years since diagnosis ("By Time Since Diagnosis",
  diagnosed 2000-2022), the shape of the survival curve.
* ``recent_5y``: 5-year relative survival for the most recent diagnosis years available
  ("5-Year Survival", 2016-2022), used to bring the curve up to date.

Suppressed or unavailable estimates are stored as null.
"""

from __future__ import annotations

import argparse
import datetime
import json
import time
import urllib.parse
from typing import Any

from ..registry import MODELS_DIR
from . import fetch

ENDPOINT = (
    "https://seer.cancer.gov/statistics-network/explorer/source/content_writers/render_region_5.php"
)
# Our key -> SEER*Explorer site code.
SITES = {
    "lung": 47, "breast": 55, "colorectal": 20, "prostate": 66, "pancreas": 40, "liver": 35,
    "stomach": 18, "esophagus": 17, "bladder": 71, "kidney": 72, "melanoma": 53, "ovary": 61,
    "cervix": 57, "uterus": 58, "thyroid": 80, "brain": 76, "nhl": 86, "hodgkin": 83,
    "myeloma": 89, "leukaemia": 90, "oral": 3, "larynx": 46, "small_intestine": 19, "anus": 34,
    "gallbladder": 38, "bone": 50, "soft_tissue": 51, "mesothelioma": 111, "testis": 67,
    "all": 1,
}  # fmt: skip
# Sex-specific sites are published for one sex only (SEER codes: 2 male, 3 female).
SEX = {"breast": 3, "ovary": 3, "cervix": 3, "uterus": 3, "prostate": 2, "testis": 2}
AGES = {"lt50": 9, "50_64": 141, "65_74": 160, "75plus": 166, "all": 1}
STAGES = {"all": "101", "localized": "104", "regional": "105", "distant": "106"}
GRAPH_CURVE, GRAPH_FIVE_YEAR = 6, 5
OUT = MODELS_DIR / "cancer" / "seer_relative_survival.json"


def _query(site: int, sex: int, age: int, graph: int, refresh: bool) -> dict[str, Any]:
    params = {
        "site": site, "data_type": 4, "graph_type": graph, "compareBy": "stage",
        **{f"chk_stage_{s}": s for s in STAGES.values()},
        "series": 9, "sex": sex, "race": 1, "age_range": age, "advopt_precision": 1, "hdn_view": 0,
    }  # fmt: skip
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    cached = fetch(url, f"seer/{site}_{sex}_{age}_{graph}.json", refresh=refresh)
    body = json.loads(cached.read_text(encoding="utf-8"))
    return json.loads(body) if isinstance(body, str) else body


def _rate(value: Any) -> float | None:
    try:
        r = float(value) / 100
    except TypeError, ValueError:
        return None
    return r if r > 0 else None


def _series(
    data: dict[str, Any], site: int, sex: int, age: int, stage: str
) -> list[list[Any]] | None:
    entry = data["data"].get(f"{sex}_1_{age}_{stage}_{site}_{site}")
    return entry["data_series"] if entry else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-download cached responses")
    args = parser.parse_args()
    out: dict[str, Any] = {
        "source": "seer_explorer",
        "retrieved": datetime.date.today().isoformat(),
        "curve_diagnosis_years": "2000-2022",
        "recent_diagnosis_years": "2016-2022",
        "sites": {},
    }
    for key, site in SITES.items():
        sex = SEX.get(key, 1)
        out["sites"][key] = {}
        for age_key, age in AGES.items():
            curve_data = _query(site, sex, age, GRAPH_CURVE, args.refresh)
            recent_data = _query(site, sex, age, GRAPH_FIVE_YEAR, args.refresh)
            stages = {}
            for stage_key, stage in STAGES.items():
                series = _series(curve_data, site, sex, age, stage) or []
                by_year = {int(row[0]): row for row in series}
                recent = _series(recent_data, site, sex, age, stage)
                stages[stage_key] = {
                    "n": by_year[1][5] if 1 in by_year else None,
                    "curve": [_rate(by_year[k][1]) if k in by_year else None for k in range(1, 11)],
                    "recent_5y": _rate(recent[0][0]) if recent else None,
                }
            out["sites"][key][age_key] = stages
            time.sleep(0.3)  # be polite to NCI's server
        print(key, "done")
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
