import math

import pytest

from general.evaluate import (
    EvaluationError,
    evaluate,
    population_cum_hazard,
    solve_time,
)


def test_weibull_layer_matches_closed_form(spec):
    # score 4 (centre) and flag false => HR 1 => exponential with mean 5 => median 5 ln 2
    result = evaluate(spec, {"age": 60, "score": 4, "flag": False})
    assert result["layer"]["id"] == "refined"
    assert result["median_years"] == pytest.approx(5 * math.log(2), abs=1e-12)
    assert result["survival_at"]["1"] == pytest.approx(math.exp(-0.2))
    assert result["range_low_years"] == pytest.approx(-5 * math.log(0.75), abs=1e-12)


def test_missing_input_is_marginalised(spec):
    # flag missing => mixture 3:1 of HR 1 and HR e^0.5
    result = evaluate(spec, {"age": 60, "score": 4})
    expected = 0.75 * math.exp(-1 / 5) + 0.25 * math.exp(-math.exp(0.5) / 5)
    assert result["survival_at"]["1"] == pytest.approx(expected)
    assert next(i for i in result["inputs"] if i["id"] == "flag")["assumed"] is not None


def test_falls_back_to_base_layer_when_requirement_missing(spec):
    result = evaluate(spec, {"age": 60, "sex": "male"})
    assert result["layer"]["id"] == "base"
    assert result["skipped_layers"] == [
        {"id": "points", "label": "Points", "lacking": ["score", "kind"]},
        {"id": "refined", "label": "Refined", "lacking": ["score"]},
        {"id": "relative", "label": "Relative", "lacking": ["kind"]},
        {"id": "points_3y", "label": "Points at 3 years", "lacking": ["flag"]},
    ]
    # score marginalised over {2, 6}: bands give HR 1 or e^0.3 on a constant q=0.1 table
    mu = -math.log(0.9)
    expected = 0.5 * math.exp(-mu) + 0.5 * math.exp(-math.exp(0.3) * mu)
    assert result["survival_at"]["1"] == pytest.approx(expected)


def test_implausible_value_is_ignored(spec):
    result = evaluate(spec, {"age": 60, "score": 99})
    assert result["layer"]["id"] == "base"
    assert next(i for i in result["inputs"] if i["id"] == "score")["status"] == "implausible"


def test_required_input_missing_raises(spec):
    with pytest.raises(EvaluationError, match="Age"):
        evaluate(spec, {"score": 4})


def test_population_cum_hazard_spans_ages():
    table = [0.1, 0.2, 0.3]
    h = population_cum_hazard(table, 0.5, 2.0)  # half of age 0, all of 1, half of 2
    expected = -(0.5 * math.log(0.9) + math.log(0.8) + 0.5 * math.log(0.7))
    assert h == pytest.approx(expected)
    # beyond the table, the last age's rate repeats
    assert population_cum_hazard(table, 5, 1) == pytest.approx(-math.log(0.7))


def test_solve_time_beyond_horizon_is_none():
    assert solve_time(lambda t: 0.99, 0.5) is None


def test_beyond_reliable_flag(spec):
    young = evaluate(spec, {"age": 30, "sex": "female", "score": 4, "flag": False})
    assert young["beyond_reliable"] is False  # Weibull median ~3.5 y
    strict = spec.model_copy(update={"max_reliable_years": 10})
    long_lived = evaluate(strict, {"age": 0, "sex": "female"})  # base layer median ~11.6 y
    assert long_lived["median_years"] > 10
    assert long_lived["beyond_reliable"] is True


def test_relative_survival_closed_form(spec):
    # kind b: R(1) = 0.5, extended at the same excess hazard (ln 2 per year), flag off => HR 1
    result = evaluate(spec, {"age": 60, "sex": "female", "kind": "b", "since": 0, "flag": False})
    assert result["layer"]["id"] == "relative"
    assert result["survival_at"]["1"] == pytest.approx(0.95 * 0.5)
    assert result["survival_at"]["3"] == pytest.approx(0.95**3 * 0.5**3)


def test_relative_survival_is_conditional_on_time_since_diagnosis(spec):
    # age 55, 10 years since diagnosis => diagnosed at 45 => the age<50 curve [0.9, 0.8],
    # whose last-year excess hazard ln(0.9/0.8) continues beyond year 2
    result = evaluate(spec, {"age": 55, "sex": "male", "kind": "a", "since": 10, "flag": False})
    assert result["survival_at"]["1"] == pytest.approx(0.9 * 0.8 / 0.9)
    later = evaluate(spec, {"age": 55, "sex": "male", "kind": "a", "since": 0.5, "flag": False})
    # diagnosed at 54.5 => all-ages curve, X(1.5) - X(0.5) on knots [0, -ln .8, -ln .6]
    x = [0.0, -math.log(0.8), -math.log(0.6)]
    expected = 0.9 * math.exp(-((x[1] + 0.5 * (x[2] - x[1])) - 0.5 * x[1]))
    assert later["survival_at"]["1"] == pytest.approx(expected)


def test_relative_survival_terms_scale_the_excess_hazard_only(spec):
    result = evaluate(spec, {"age": 60, "sex": "female", "kind": "b", "since": 0, "flag": True})
    assert result["survival_at"]["1"] == pytest.approx(0.95 * 0.5 ** math.exp(0.5))


def test_score_weibull_joins_the_published_points(spec):
    # age 70, score 6 => grid row "score >= 5", band "age >= 50" => 2, flag => +1, score 3
    result = evaluate(spec, {"age": 70, "sex": "male", "kind": "a", "score": 6, "flag": True})
    assert result["layer"]["id"] == "points"
    assert result["survival_at"]["1"] == pytest.approx(0.6)
    assert result["survival_at"]["3"] == pytest.approx(0.2)
    k = math.log(math.log(0.2) / math.log(0.6)) / math.log(3)
    assert result["survival_at"]["5"] == pytest.approx(math.exp(math.log(0.6) * 5**k))


def test_score_weibull_is_capped_at_population_survival(spec):
    # score 0 => published S(1) = 0.95, but a male on the flat table survives 0.9 a year
    result = evaluate(spec, {"age": 40, "sex": "male", "kind": "a", "score": 2, "flag": False})
    assert result["survival_at"]["1"] == pytest.approx(0.9)


def test_identical_mixture_components_are_merged(spec):
    # flag missing (3:1) and sex missing (1:1): four combinations, each a distinct score/sex key
    result = evaluate(spec, {"age": 40, "kind": "a", "score": 2})
    s0 = 0.5 * 0.9 + 0.5 * 0.95  # score 0, capped for males at 0.9, females at 0.95
    s1 = 0.8  # score 1: below both populations
    assert result["survival_at"]["1"] == pytest.approx(0.75 * s0 + 0.25 * s1)


def test_when_skips_layer_for_other_values(spec):
    result = evaluate(spec, {"age": 60, "kind": "b", "score": 4, "flag": False})
    assert result["layer"]["id"] == "refined"
    assert result["skipped_layers"][0]["lacking"] == ["kind"]


def test_score_life_table_hits_the_published_point_and_follows_ageing(spec):
    # age 75 => score 2 => S(3) = 0.5, flat female table q = 0.05 => HR = ln 2 / (-3 ln 0.95)
    result = evaluate(spec, {"age": 75, "sex": "female", "flag": True})
    assert result["layer"]["id"] == "points_3y"
    assert result["survival_at"]["3"] == pytest.approx(0.5)
    hr = math.log(2) / (-3 * math.log(0.95))
    assert result["survival_at"]["1"] == pytest.approx(0.95**hr)


def test_score_life_table_is_never_better_than_population(spec):
    # age 30 => score 0 => published S(3) = 0.95 > male population 0.9**3: HR floored at 1
    result = evaluate(spec, {"age": 30, "sex": "male", "flag": True})
    assert result["survival_at"]["3"] == pytest.approx(0.9**3)
