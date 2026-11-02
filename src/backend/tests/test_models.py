"""Checks on the real models and their published source data."""

from __future__ import annotations

import math

import pytest

from deaths_warrant.evaluate import evaluate, population_cum_hazard
from deaths_warrant.registry import MODELS_DIR, ModelFolder, discover, load_life_table
from deaths_warrant.spec import RelativeSurvival

CANCER = ModelFolder("cancer", MODELS_DIR / "cancer").load()


@pytest.mark.parametrize(
    ("sex", "age", "published"),
    # Life expectancy e(x), NCHS United States life tables 2024 (NVSR 75-5, tables 2 and 3)
    [("male", 65, 18.359), ("female", 65, 20.831), ("male", 80, 8.629), ("female", 80, 9.915)],
)
def test_us_life_table_reproduces_published_life_expectancy(sex, age, published):
    q = getattr(load_life_table("us_2024"), sex)
    step = 0.01
    e = sum(math.exp(-population_cum_hazard(q, age, k * step)) * step for k in range(6000))
    assert e == pytest.approx(published, abs=0.02)


def test_every_real_model_builds_and_reports_validation():
    for folder in discover():
        spec = folder.load().build()
        assert spec.validation, f"{spec.id} has no published validation results"
        assert all(v.n >= 20 for v in spec.validation)


def test_cancer_curves_are_recency_calibrated_within_bounds():
    spec = CANCER.build()
    for layer in spec.layers:
        assert isinstance(layer.survival, RelativeSurvival)
        assert all(len(c.relative) == 10 for c in layer.survival.curves)
    lo, hi = CANCER.RECENCY_BOUNDS
    cell = CANCER.SEER["sites"]["lung"]["65_74"]["distant"]
    curve, _ = CANCER.relative_curve("lung", "65_74", "distant")
    k = math.log(curve[4]) / math.log(cell["curve"][4])
    assert lo <= k <= hi
    assert curve[4] == pytest.approx(cell["recent_5y"], abs=1e-6)  # matches 2016-2022 SEER


def test_cancer_newly_diagnosed_one_year_survival_is_population_times_relative():
    spec = CANCER.build()
    result = evaluate(
        spec, {"age": 70, "sex": "male", "site": "lung", "stage": "distant", "since": 0}
    )
    q = load_life_table("us_2024").male
    expected = (
        math.exp(-population_cum_hazard(q, 70, 1))
        * CANCER.relative_curve("lung", "65_74", "distant")[0][0]
    )  # noqa: E501
    assert result["survival_at"]["1"] == pytest.approx(expected)


def test_cancer_falls_back_when_stage_or_site_missing():
    spec = CANCER.build()
    assert evaluate(spec, {"age": 60, "site": "breast"})["layer"]["id"] == "site"
    assert evaluate(spec, {"age": 60, "stage": "distant"})["layer"]["id"] == "all_sites"


def test_cancer_survival_since_diagnosis_improves_prognosis():
    spec = CANCER.build()
    base = {"age": 60, "sex": "female", "site": "colorectal", "stage": "regional"}
    new = evaluate(spec, {**base, "since": 0})["survival_at"]["5"]
    survivor = evaluate(spec, {**base, "since": 5})["survival_at"]["5"]
    assert survivor > new  # conditional survival: having survived 5 years is good news
