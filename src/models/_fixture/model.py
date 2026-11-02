"""Unit-test fixture model (not a real model, not patient data).

Round-number coefficients make the maths checkable by hand. It is exported like a real model
so the TypeScript evaluator is held to the Python reference before any disease model exists.
The picker never shows it: folders starting with ``_`` are excluded from the app.
"""

from deaths_warrant.spec import ModelSpec

FIXTURE_SPEC = {
    "id": "fixture",
    "name": "Fixture",
    "version": "0.0.0",
    "description": "Unit-test spec",
    "group_codes": {"icd10": ["X99"]},
    "inputs": [
        {
            "id": "age",
            "label": "Age",
            "type": "number",
            "min": 0,
            "max": 120,
            "extract": {"rule": "age"},
        },
        {
            "id": "sex",
            "label": "Sex",
            "type": "enum",
            "values": ["female", "male"],
            "extract": {"rule": "sex"},
            "missing": [{"value": "female", "weight": 1}, {"value": "male", "weight": 1}],
        },
        {
            "id": "score",
            "label": "Score",
            "type": "number",
            "min": 0,
            "max": 10,
            "extract": {"rule": "observation_number", "loinc": ["0000-0"], "units": {"": 1}},
            "missing": [{"value": 2, "weight": 1}, {"value": 6, "weight": 1}],
        },
        {
            "id": "flag",
            "label": "Flag",
            "type": "boolean",
            "extract": {"rule": "condition_present", "codes": {"icd10": ["X991"]}},
            "missing": [{"value": False, "weight": 3}, {"value": True, "weight": 1}],
        },
    ],
    "layers": [
        {
            "id": "refined",
            "label": "Refined",
            "description": "Weibull",
            "requires": ["score"],
            "survival": {
                "type": "weibull_ph",
                "shape": 1.0,
                "scale_years": 5.0,
                "terms": [
                    {"kind": "linear", "input": "score", "coef": 0.1, "center": 4},
                    {"kind": "category", "input": "flag", "values": {"true": 0.5, "false": 0.0}},
                ],
            },
        },
        {
            "id": "base",
            "label": "Base",
            "description": "Life table",
            "survival": {
                "type": "life_table_ph",
                "life_table": "flat",
                "terms": [
                    {
                        "kind": "bands",
                        "input": "score",
                        "bands": [{"lt": 5, "value": 0.0}, {"lt": None, "value": 0.3}],
                    },
                ],
            },
        },
    ],
    "life_tables": {"flat": {"source": "test", "female": [0.05, 0.05], "male": [0.1, 0.1]}},
}


def build() -> ModelSpec:
    return ModelSpec.model_validate(FIXTURE_SPEC)


def golden_inputs() -> list[dict]:
    return [
        {"age": 60, "score": 4, "flag": False},
        {"age": 60, "score": 4},
        {"age": 60, "sex": "male"},
        {"age": 70.5, "sex": "female", "score": 6, "flag": True},
        {"age": 60, "score": 99},
        {"age": 0, "sex": "female"},
    ]
