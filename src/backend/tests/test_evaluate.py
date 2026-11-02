import math

import pytest

from deaths_warrant.evaluate import (
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
    assert result["skipped_layers"] == [{"id": "refined", "label": "Refined", "lacking": ["score"]}]
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
