"""Discovers model folders: ``src/models/<id>/model.py``.

A model module must define:

* ``build() -> ModelSpec`` — the full spec, coefficients included.
* ``golden_inputs() -> list[dict]`` — observed-input sets covering every layer; the exporter
  evaluates them and writes ``golden.json`` so the browser evaluator can be checked against it.

Folders starting with ``_`` are not shown in the app: ``_shared`` holds shared data and
``_fixture`` is a unit-test model that is exported only so the browser evaluator can be tested.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from .spec import LifeTable

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
SHARED_DIR = MODELS_DIR / "_shared"


@dataclass(frozen=True)
class ModelFolder:
    id: str
    path: Path

    def load(self) -> ModuleType:
        spec = importlib.util.spec_from_file_location(f"dw_model_{self.id}", self.path / "model.py")
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {self.path / 'model.py'}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def discover(models_dir: Path = MODELS_DIR, *, include_fixture: bool = False) -> list[ModelFolder]:
    return [
        ModelFolder(p.parent.name, p.parent)
        for p in sorted(models_dir.glob("*/model.py"))
        if not p.parent.name.startswith("_") or (include_fixture and p.parent.name == "_fixture")
    ]


def load_life_table(name: str) -> LifeTable:
    """Load ``_shared/life_tables/<name>.json`` (see that folder's README for provenance)."""
    with open(SHARED_DIR / "life_tables" / f"{name}.json", encoding="utf-8") as f:
        return LifeTable.model_validate(json.load(f))
