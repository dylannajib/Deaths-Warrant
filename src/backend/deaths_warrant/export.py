"""Export every model's ``spec.json`` and ``golden.json``.

python -m deaths_warrant.export          # (re)write the files
python -m deaths_warrant.export --check  # CI: fail if committed files are stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .evaluate import evaluate
from .registry import ModelFolder, discover
from .spec import ModelSpec

GOLDEN_KEYS = ("layer", "median_years", "range_low_years", "range_high_years", "survival_at")


def render(folder: ModelFolder) -> dict[str, str]:
    module = folder.load()
    spec: ModelSpec = module.build()
    if spec.id != folder.id.removeprefix("_"):
        raise ValueError(f"{folder.path}: spec id {spec.id!r} must match folder name")
    golden: list[dict[str, Any]] = []
    for observed in module.golden_inputs():
        result = evaluate(spec, observed)
        golden.append({"observed": observed, "expected": {k: result[k] for k in GOLDEN_KEYS}})
    layers_hit = {g["expected"]["layer"]["id"] for g in golden}
    if layers_hit != {layer.id for layer in spec.layers}:
        raise ValueError(f"{folder.id}: golden inputs must exercise every layer")
    return {
        "spec.json": _dump(spec.model_dump(mode="json")),
        "golden.json": _dump(golden),
    }


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    args = parser.parse_args(argv)
    stale: list[Path] = []
    for folder in discover(include_fixture=True):
        for name, content in render(folder).items():
            path = folder.path / name
            if args.check:
                if not path.exists() or path.read_text(encoding="utf-8") != content:
                    stale.append(path)
            else:
                path.write_text(content, encoding="utf-8")
                print(f"wrote {path}")
    if stale:
        print("Stale exports (run `python -m deaths_warrant.export`):", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
