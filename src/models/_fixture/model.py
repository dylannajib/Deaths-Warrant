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
        {
            "id": "kind",
            "label": "Kind",
            "type": "enum",
            "values": ["a", "b"],
            "extract": {
                "rule": "condition_category",
                "categories": [{"value": "a", "codes": {"icd10": ["X98"]}}],
            },
            "missing": [],
        },
        {
            "id": "since",
            "label": "Years since diagnosis",
            "type": "number",
            "min": 0,
            "max": 60,
            "extract": {"rule": "years_since_condition", "codes": {"icd10": ["X98"]}},
            "missing": [{"value": 0, "weight": 1}],
        },
    ],
    "layers": [
        {
            "id": "points",
            "label": "Points",
            "description": "Integer score table",
            "requires": ["score"],
            "when": {"kind": ["a"]},
            "survival": {
                "type": "score_weibull",
                "times": [1, 3],
                "survival": [[0.95, 0.9], [0.8, 0.5], [0.7, 0.4], [0.6, 0.2]],
                "life_table": "flat",
                "terms": [
                    {
                        "kind": "grid",
                        "input": "score",
                        "by": "age",
                        "rows": [
                            {"lt": 5, "bands": [{"lt": 50, "value": 0}, {"lt": None, "value": 1}]},
                            {
                                "lt": None,
                                "bands": [{"lt": 50, "value": 1}, {"lt": None, "value": 2}],
                            },
                        ],
                    },
                    {"kind": "category", "input": "flag", "values": {"true": 1, "false": 0}},
                ],
            },
        },
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
            "id": "relative",
            "label": "Relative",
            "description": "Relative survival",
            "requires": ["kind"],
            "survival": {
                "type": "relative_survival",
                "life_table": "flat",
                "since_input": "since",
                "keys": ["kind"],
                "curves": [
                    {"match": {"kind": "a"}, "age_lt": 50, "relative": [0.9, 0.8]},
                    {"match": {"kind": "a"}, "relative": [0.8, 0.6, 0.5]},
                    {"match": {"kind": "b"}, "relative": [0.5]},
                ],
                "terms": [
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
        {"age": 60, "sex": "female", "kind": "a", "since": 0},
        {"age": 55, "sex": "male", "kind": "a", "since": 10},
        {"age": 60, "kind": "b"},
        {"age": 70, "sex": "male", "kind": "a", "score": 6, "flag": True},
        {"age": 40, "kind": "a", "score": 2},
    ]
