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


CARDIO = ModelFolder("cardiovascular", MODELS_DIR / "cardiovascular").load()
NO_CVD = {
    "heart_failure": False,
    "coronary": False,
    "stroke": False,
    "atrial_fibrillation": False,
    "peripheral_artery": False,
    "cardiomyopathy": False,
    "diabetes": False,
    "copd": False,
}


def test_maggic_score_matches_hand_calculation_and_table_4():
    # Pocock 2013 Figure 2: EF 25 -> 5; age 72 with EF < 30 -> 6; SBP 105 with EF < 30 -> 5;
    # BMI 23 -> 3; creatinine 160 -> 4; NYHA III -> 6; male -> 1; diabetes -> 3;
    # HF >= 18 months -> 2; on beta-blocker and ACE-I -> 0. Total 35.
    spec = CARDIO.build()
    observed = {
        **NO_CVD, "heart_failure": True, "diabetes": True, "age": 72, "sex": "male", "ef": 25,
        "sbp": 105, "bmi": 23, "creatinine": 160, "nyha": "III", "smoker": "not_current",
        "hf_years": 4, "beta_blocker": True, "acei_arb": True,
    }  # fmt: skip
    result = evaluate(spec, observed)
    assert result["layer"]["id"] == "maggic"
    assert result["survival_at"]["1"] == pytest.approx(1 - 0.369)
    assert result["survival_at"]["3"] == pytest.approx(1 - 0.692)


def test_maggic_never_beats_population_survival():
    # A young, low-score patient: published MAGGIC survival would exceed the population's
    spec = CARDIO.build()
    observed = {
        **NO_CVD, "heart_failure": True, "age": 40, "sex": "female", "ef": 60, "sbp": 160,
        "bmi": 32, "creatinine": 70, "nyha": "I", "smoker": "not_current", "hf_years": 0.5,
        "beta_blocker": True, "acei_arb": True,
    }  # fmt: skip
    q = load_life_table("us_2024").female
    s30 = next(s for t, s in evaluate(spec, observed)["curve"] if t == 30)
    assert s30 <= math.exp(-population_cum_hazard(q, 40, 30)) + 1e-12


def test_recent_heart_failure_admission_takes_unrecorded_nyha_as_class_iv():
    spec = CARDIO.build()
    observed = {
        **NO_CVD, "heart_failure": True, "age": 75, "sex": "male", "ef": 30, "sbp": 115,
        "bmi": 26, "creatinine": 120, "smoker": "not_current", "hf_years": 3,
        "beta_blocker": True, "acei_arb": True,
    }  # fmt: skip
    admitted = evaluate(spec, {**observed, "hf_admission": True})
    class_iv = evaluate(spec, {**observed, "nyha": "IV"})
    averaged = evaluate(spec, observed)
    assert admitted["layer"]["id"] == "maggic_admitted"
    assert averaged["layer"]["id"] == "maggic"
    assert admitted["survival_at"] == pytest.approx(class_iv["survival_at"], abs=1e-12)
    assert admitted["survival_at"]["1"] < averaged["survival_at"]["1"]
    # A NYHA class in the record is used as recorded.
    recorded = evaluate(spec, {**observed, "hf_admission": True, "nyha_admitted": "II"})
    assert recorded["survival_at"] == pytest.approx(
        evaluate(spec, {**observed, "nyha": "II"})["survival_at"], abs=1e-12
    )


def test_heart_failure_without_ef_reproduces_taylor_2019():
    spec = CARDIO.build()
    for _, age, published in CARDIO.TAYLOR_SURVIVAL[:3]:
        obs = {**NO_CVD, "heart_failure": True, "age": age, "hf_years": 0}
        male = evaluate(spec, {**obs, "sex": "male"})
        female = evaluate(spec, {**obs, "sex": "female"})
        assert male["layer"]["id"] == "heart_failure"
        mix = CARDIO.TAYLOR_MALE * male["survival_at"]["5"]
        mix += (1 - CARDIO.TAYLOR_MALE) * female["survival_at"]["5"]
        assert mix == pytest.approx(published[5], abs=1e-6)


def test_stroke_layer_reproduces_tong_2021_five_year_survival():
    spec = CARDIO.build()
    for _, age, published in CARDIO.TONG_SURVIVAL_5Y:
        obs = {**NO_CVD, "stroke": True, "stroke_years": 0, "age": age}
        male = evaluate(spec, {**obs, "sex": "male"})
        female = evaluate(spec, {**obs, "sex": "female"})
        assert male["layer"]["id"] == "stroke"
        mix = CARDIO.TONG_MALE * male["survival_at"]["5"]
        mix += (1 - CARDIO.TONG_MALE) * female["survival_at"]["5"]
        assert mix == pytest.approx(published, abs=2e-6)
    # Surviving the first years improves the outlook; an undated stroke uses the base layer.
    later = evaluate(spec, {**NO_CVD, "stroke": True, "stroke_years": 2, "age": 80, "sex": "male"})
    first = evaluate(spec, {**NO_CVD, "stroke": True, "stroke_years": 0, "age": 80, "sex": "male"})
    assert later["survival_at"]["1"] > first["survival_at"]["1"]
    undated = evaluate(spec, {**NO_CVD, "stroke": True, "age": 80, "sex": "male"})
    assert undated["layer"]["id"] == "base"


def test_other_cardiovascular_conditions_multiply_hazard_ratios():
    spec = CARDIO.build()
    base = {**NO_CVD, "age": 66, "sex": "female"}
    q = load_life_table("us_2024").female
    h = population_cum_hazard(q, 66, 1)
    both = evaluate(spec, {**base, "coronary": True, "stroke": True})
    assert both["layer"]["id"] == "base"
    assert both["survival_at"]["1"] == pytest.approx(math.exp(-2.0 * 2.1 * h), rel=1e-5)


RESP = ModelFolder("respiratory", MODELS_DIR / "respiratory").load()
NO_CLRD = {"copd": False, "bronchiectasis": False, "asthma": False}


def test_updated_ado_score_matches_hand_calculation_and_table():
    # Puhan 2012 Table 3: FEV1 42% -> 3; mMRC 3 -> 2; age 68 -> 4. Score 9 -> 20.1% at 3 years
    spec = RESP.build()
    obs = {**NO_CLRD, "copd": True, "age": 68, "sex": "male", "fev1_pct": 42, "mmrc": 3}
    result = evaluate(spec, obs)
    assert result["layer"]["id"] == "ado"
    assert result["survival_at"]["3"] == pytest.approx(1 - 0.201)


def test_ado_follows_ageing_through_the_published_point():
    spec = RESP.build()
    obs = {**NO_CLRD, "copd": True, "age": 68, "sex": "male", "fev1_pct": 42, "mmrc": 3}
    q = load_life_table("us_2024").male
    hr = -math.log(1 - 0.201) / population_cum_hazard(q, 68, 3)
    assert evaluate(spec, obs)["survival_at"]["1"] == pytest.approx(
        math.exp(-hr * population_cum_hazard(q, 68, 1))
    )
