import json
import textwrap

import pytest

from deaths_warrant.export import render
from deaths_warrant.registry import discover

from .conftest import FIXTURE_SPEC


def write_model(tmp_path, golden_inputs):
    folder = tmp_path / "fixture"
    folder.mkdir()
    (folder / "spec_data.json").write_text(json.dumps(FIXTURE_SPEC))
    (folder / "model.py").write_text(
        textwrap.dedent(f"""
        import json
        from pathlib import Path
        from deaths_warrant.spec import ModelSpec

        def build():
            data = (Path(__file__).parent / "spec_data.json").read_text()
            return ModelSpec.model_validate_json(data)

        def golden_inputs():
            return {golden_inputs!r}
        """)
    )
    (tmp_path / "_shared").mkdir()
    return tmp_path


def test_discover_skips_shared_and_renders(tmp_path):
    models = write_model(
        tmp_path,
        [
            {"age": 60, "kind": "a", "score": 1},
            {"age": 60, "score": 4},
            {"age": 60, "kind": "b"},
            {"age": 60, "flag": True},
            {"age": 60},
        ],
    )
    folders = discover(models)
    assert [f.id for f in folders] == ["fixture"]
    files = render(folders[0])
    golden = json.loads(files["golden.json"])
    assert [g["expected"]["layer"]["id"] for g in golden] == [
        "points",
        "refined",
        "relative",
        "points_3y",
        "base",
    ]
    assert json.loads(files["spec.json"])["id"] == "fixture"


def test_golden_inputs_must_cover_every_layer(tmp_path):
    models = write_model(tmp_path, [{"age": 60, "score": 4}])
    with pytest.raises(ValueError, match="every layer"):
        render(discover(models)[0])
