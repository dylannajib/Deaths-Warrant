"""Helpers shared by model authors (``src/models/<id>/model.py``).

They build plain spec dictionaries. ``ModelSpec`` still validates everything a model returns.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple


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


def bands(cuts: list[tuple[float | None, float]]) -> list[dict[str, Any]]:
    """Band term entries from (exclusive upper bound or None, value) pairs."""
    return [{"lt": lt, "value": v} for lt, v in cuts]


def validation_results(*files: Path) -> list[dict[str, Any]]:
    """Results written by the model's validation scripts (absent files are skipped)."""
    return [r for f in files if f.exists() for r in json.loads(f.read_text("utf-8"))["results"]]
