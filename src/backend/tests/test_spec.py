import copy

import pytest
from pydantic import ValidationError

from deaths_warrant.spec import ModelSpec

from .conftest import FIXTURE_SPEC


def mutated(**changes):
    data = copy.deepcopy(FIXTURE_SPEC)
    for path, value in changes.items():
        target = data
        *parents, leaf = path.split("__")
        for key in parents:
            target = target[int(key)] if key.isdigit() else target[key]
        target[leaf] = value
    return data


def test_fixture_is_valid():
    ModelSpec.model_validate(FIXTURE_SPEC)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"layers__1__requires": ["score"]}, "last layer"),
        ({"layers__0__requires": ["nope"]}, "unknown input"),
        ({"layers__1__survival__life_table": "nope"}, "unknown life table"),
        ({"inputs__1__missing": [{"value": "other", "weight": 1}]}, "wrong type"),
        (
            {
                "layers__0__survival__terms": [
                    {"kind": "category", "input": "flag", "values": {"true": 1}}
                ]
            },
            "cover exactly",
        ),
        (
            {"layers__0__survival__terms": [{"kind": "linear", "input": "flag", "coef": 1}]},
            "needs a number",
        ),
        ({"group_codes": {"icd10": ["i50.1"]}}, "upper-case"),
        (
            {"life_tables": {"flat": {"source": "x", "female": [1.0, 0.5], "male": [0.1, 0.1]}}},
            r"\[0, 1\)",
        ),
        ({"surprise": True}, "Extra inputs"),
    ],
)
def test_invalid_specs_rejected(changes, message):
    with pytest.raises(ValidationError, match=message):
        ModelSpec.model_validate(mutated(**changes))
