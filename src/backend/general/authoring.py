"""Helpers shared by model authors (``src/prognosis-models/<id>/model.py``).

They build plain spec dictionaries. ``ModelSpec`` still validates everything a model returns.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, NamedTuple

from .evaluate import population_cum_hazard
from .spec import LifeTable

# The U.S. life table every model uses (loaded with registry.load_life_table("us_2024")).
NCHS_US_2024 = {
    "id": "nchs_us_2024",
    "citation": (
        "Arias E, Xu JQ, Kochanek K. United States life tables, 2024. National Vital"
        " Statistics Reports vol 75 no 5. National Center for Health Statistics."
    ),
    "url": "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/NVSR/75-05/",
    "licence": "U.S. Government work (public domain)",
}


def population_survival(table: LifeTable, age: float, t: float, male: float) -> float:
    """Population survival to t from age for a cohort with the given male share."""
    return male * math.exp(-population_cum_hazard(table.male, age, t)) + (1 - male) * math.exp(
        -population_cum_hazard(table.female, age, t)
    )


class Condition(NamedTuple):
    """A recorded diagnosis that a model scores, with its published all-cause hazard ratio."""

    label: str
    icd10: list[str]
    icd9: list[str]
    hr: float | None  # None: the condition has its own layer instead of a ratio
    source: str


def load_json(folder: Path, name: str) -> Any:
    return json.loads((folder / name).read_text("utf-8"))


def snomed_sets(folder: Path) -> dict[str, list[str]]:
    """The model's expanded SNOMED CT sets (``snomed_sets.json``, see sources/snomed.py)."""
    return load_json(folder, "snomed_sets.json")["sets"]


def codes(condition: Condition, snomed: list[str]) -> dict[str, list[str]]:
    """Code set of a condition for extraction rules."""
    return {"icd10": condition.icd10, "icd9": condition.icd9, "snomed": snomed}


def condition_present(codes: dict[str, list[str]]) -> dict[str, Any]:
    return {"rule": "condition_present", "codes": codes}


def group_codes(
    conditions: dict[str, Condition], snomed: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Every code of the given conditions. A record with none of them is refused."""
    return {
        "icd10": sorted({p for c in conditions.values() for p in c.icd10}),
        "icd9": sorted({p for c in conditions.values() for p in c.icd9}),
        "snomed": sorted({c for key in conditions for c in snomed[key]}, key=int),
    }


def hr_term(input_id: str, hr: float) -> dict[str, Any]:
    """Log hazard ratio applied when a boolean input is true."""
    return {
        "kind": "category",
        "input": input_id,
        "values": {"true": round(math.log(hr), 6), "false": 0.0},
    }


def bands(cuts: list[tuple[float | None, float]]) -> list[dict[str, Any]]:
    """Band term entries from (exclusive upper bound or None, value) pairs."""
    return [{"lt": lt, "value": v} for lt, v in cuts]


def validation_results(*files: Path) -> list[dict[str, Any]]:
    """Results written by the model's validation scripts (absent files are skipped)."""
    return [r for f in files if f.exists() for r in json.loads(f.read_text("utf-8"))["results"]]
