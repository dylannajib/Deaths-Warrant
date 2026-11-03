"""Reference evaluator for model specs.

The browser runs ``src/frontend/src/engine/evaluate.ts``, a line-for-line port of this module.
``golden.json`` files generated here pin both implementations to the same numbers, so any
change to the algorithm must be made in both places (CI fails otherwise).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .spec import (
    BandsTerm,
    CategoryTerm,
    GridTerm,
    LifeTable,
    LifeTablePH,
    LinearTerm,
    ModelSpec,
    RelativeSurvival,
    RelativeSurvivalCurve,
    ScoreLifeTable,
    ScoreWeibull,
    Term,
    Value,
    WeibullPH,
    layer_inputs,
    term_inputs,
)

HORIZON_YEARS = 60.0
BISECTION_STEPS = 64
CURVE_STEP_YEARS = 0.25
CURVE_END_YEARS = 30.0
SURVIVAL_TIMES = (1, 3, 5)

Observed = Mapping[str, Value | None]
SurvivalFn = Callable[[float], float]


class EvaluationError(ValueError):
    """The record lacks something the model cannot do without (e.g. birth date)."""


@dataclass(frozen=True)
class _Resolved:
    values: dict[str, Value]  # usable observed values
    status: dict[str, str]  # observed | missing | implausible


def resolve_inputs(spec: ModelSpec, observed: Observed) -> _Resolved:
    values: dict[str, Value] = {}
    status: dict[str, str] = {}
    for i in spec.inputs:
        v = observed.get(i.id)
        if v is None:
            status[i.id] = "missing"
        elif i.accepts(v):
            values[i.id] = v
            status[i.id] = "observed"
        else:
            status[i.id] = "implausible"
        if i.id not in values and i.missing is None:
            raise EvaluationError(f"{i.label} is required but was not found in the record")
    return _Resolved(values, status)


def _band(bands: list, x: float):
    for band in bands:
        if band.lt is None or x < band.lt:
            return band
    raise AssertionError("unreachable: the last band is a catch-all")


def term_value(term: Term, values: Mapping[str, Value]) -> float:
    x = values[term.input]
    if isinstance(term, GridTerm):
        return _band(_band(term.rows, float(x)).bands, float(values[term.by])).value
    if isinstance(term, LinearTerm):
        xf = float(x)
        if term.min is not None:
            xf = max(xf, term.min)
        if term.max is not None:
            xf = min(xf, term.max)
        return term.coef * (xf - term.center)
    if isinstance(term, BandsTerm):
        return _band(term.bands, float(x)).value
    assert isinstance(term, CategoryTerm)
    key = ("true" if x else "false") if isinstance(x, bool) else str(x)
    return term.values[key]


def population_cum_hazard(table: list[float], age: float, t: float) -> float:
    """Cumulative hazard over [age, age + t], constant hazard within each year of age."""
    end = age + t
    total = 0.0
    x = age
    while x < end:
        i = math.floor(x)
        nxt = min(i + 1.0, end)
        q = table[min(i, len(table) - 1)]
        total += -math.log1p(-q) * (nxt - x)
        x = nxt
    return total


def excess_knots(relative: list[float]) -> list[float]:
    """Excess cumulative hazard -ln R(k) at whole years k = 0..n."""
    return [0.0, *(-math.log(r) for r in relative)]


def excess_cum_hazard(knots: list[float], t: float) -> float:
    """Linear between whole years; beyond the last year the last year's slope continues."""
    n = len(knots) - 1
    if t >= n:
        return knots[n] + (knots[n] - knots[n - 1]) * (t - n)
    k = math.floor(t)
    return knots[k] + (knots[k + 1] - knots[k]) * (t - k)


def select_curve(survival: RelativeSurvival, values: Mapping[str, Value]) -> RelativeSurvivalCurve:
    """First curve matching the keys and the age at diagnosis (age - years since diagnosis)."""
    age_at_diagnosis = float(values[survival.age_input]) - float(values[survival.since_input])
    for c in survival.curves:
        if all(values[k] == v for k, v in c.match.items()) and (
            c.age_lt is None or age_at_diagnosis < c.age_lt
        ):
            return c
    raise AssertionError("unreachable: the spec guarantees an all-ages curve")


def score_of(survival: ScoreWeibull | ScoreLifeTable, values: Mapping[str, Value]) -> int:
    """Integer risk score: the rounded term sum, clamped to the published table."""
    total = 0.0
    for term in survival.terms:
        total += term_value(term, values)
    return min(max(round(total), 0), len(survival.survival) - 1)


def _survival_fn(
    spec: ModelSpec, layer_index: int, values: Mapping[str, Value]
) -> tuple[tuple[Any, ...] | None, SurvivalFn]:
    """The survival function for one set of input values, plus a key: combinations with equal
    keys have identical functions, so a mixture can merge them (None = never merged)."""
    survival = spec.layers[layer_index].survival
    if isinstance(survival, ScoreWeibull):
        return _score_weibull_fn(spec, survival, values)
    if isinstance(survival, ScoreLifeTable):
        return _score_life_table_fn(spec, survival, values)
    lp = 0.0
    for term in survival.terms:
        lp += term_value(term, values)
    hr = math.exp(lp)
    if isinstance(survival, WeibullPH):
        shape, scale = survival.shape, survival.scale_years
        return None, lambda t: math.exp(-hr * (t / scale) ** shape)
    assert isinstance(survival, LifeTablePH | RelativeSurvival)
    q = _sex_table(spec, survival.life_table, values[survival.sex_input])
    age = float(values[survival.age_input])
    if isinstance(survival, LifeTablePH):
        return None, lambda t: math.exp(-hr * population_cum_hazard(q, age, t))
    since = float(values[survival.since_input])
    knots = excess_knots(select_curve(survival, values).relative)
    x0 = excess_cum_hazard(knots, since)
    return None, lambda t: math.exp(
        -population_cum_hazard(q, age, t) - hr * (excess_cum_hazard(knots, since + t) - x0)
    )


def _sex_table(spec: ModelSpec, name: str, sex: Value) -> list[float]:
    table: LifeTable = spec.life_tables[name]
    return table.female if sex == "female" else table.male


def _score_life_table_fn(
    spec: ModelSpec, survival: ScoreLifeTable, values: Mapping[str, Value]
) -> tuple[tuple[Any, ...], SurvivalFn]:
    score = score_of(survival, values)
    sex = values[survival.sex_input]
    q = _sex_table(spec, survival.life_table, sex)
    age = float(values[survival.age_input])
    h_pop = population_cum_hazard(q, age, survival.time)
    hr = max(1.0, -math.log(survival.survival[score]) / h_pop)
    return (score, age, sex), lambda t: math.exp(-hr * population_cum_hazard(q, age, t))


def _score_weibull_fn(
    spec: ModelSpec, survival: ScoreWeibull, values: Mapping[str, Value]
) -> tuple[tuple[Any, ...], SurvivalFn]:
    score = score_of(survival, values)
    (t1, t2), (s1, s2) = survival.times, survival.survival[score]
    h1 = -math.log(s1)
    k = math.log(math.log(s2) / math.log(s1)) / math.log(t2 / t1)

    def weibull(t: float) -> float:
        return math.exp(-h1 * (t / t1) ** k)

    if survival.life_table is None:
        return (score,), weibull
    sex = values[survival.sex_input]
    q = _sex_table(spec, survival.life_table, sex)
    age = float(values[survival.age_input])
    return (score, age, sex), lambda t: min(weibull(t), math.exp(-population_cum_hazard(q, age, t)))


def solve_time(s: SurvivalFn, p: float) -> float | None:
    """Smallest t with S(t) = p, or None if S stays above p up to the horizon."""
    if s(HORIZON_YEARS) > p:
        return None
    lo, hi = 0.0, HORIZON_YEARS
    for _ in range(BISECTION_STEPS):
        mid = (lo + hi) / 2
        if s(mid) > p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass(frozen=True)
class _Mixture:
    resolved: _Resolved
    layer_index: int
    skipped: list[dict[str, Any]]
    used: list[str]
    unknown: list[str]
    survival: SurvivalFn


def _mixture(spec: ModelSpec, observed: Observed) -> _Mixture:
    """Choose the layer, then average its survival over the missing inputs' distributions."""
    resolved = resolve_inputs(spec, observed)
    skipped = []
    layer_index = 0
    for layer_index, layer in enumerate(spec.layers):  # noqa: B007 - used after the loop
        lacking = [r for r in layer.requires if r not in resolved.values]
        lacking += [n for n, allowed in layer.when.items() if resolved.values.get(n) not in allowed]
        if not lacking:
            break
        skipped.append({"id": layer.id, "label": layer.label, "lacking": lacking})
    layer = spec.layers[layer_index]
    inputs = {i.id: i for i in spec.inputs}
    used = layer_inputs(layer)
    unknown = [n for n in used if n not in resolved.values]

    fns: list[SurvivalFn] = []
    weights: list[float] = []
    slots: dict[tuple[Any, ...], int] = {}
    for combo in itertools.product(*(inputs[n].missing or [] for n in unknown)):
        values = dict(resolved.values)
        weight = 1.0
        for name, wv in zip(unknown, combo, strict=True):
            values[name] = wv.value
            weight *= wv.weight
        key, fn = _survival_fn(spec, layer_index, values)
        if key is not None and key in slots:
            weights[slots[key]] += weight
            continue
        if key is not None:
            slots[key] = len(fns)
        fns.append(fn)
        weights.append(weight)
    total_weight = sum(weights)

    def s(t: float) -> float:
        acc = 0.0
        for fn, w in zip(fns, weights, strict=True):
            acc += w * fn(t)
        return acc / total_weight

    return _Mixture(resolved, layer_index, skipped, used, unknown, s)


def survival_function(spec: ModelSpec, observed: Observed) -> SurvivalFn:
    """S(t) for a record (Python-side helper for validation, e.g. life expectancy)."""
    return _mixture(spec, observed).survival


def evaluate(spec: ModelSpec, observed: Observed) -> dict[str, Any]:
    m = _mixture(spec, observed)
    resolved, skipped, used, unknown, s = m.resolved, m.skipped, m.used, m.unknown, m.survival
    layer = spec.layers[m.layer_index]

    median = solve_time(s, 0.5)
    steps = round(CURVE_END_YEARS / CURVE_STEP_YEARS)
    return {
        "model": spec.id,
        "model_version": spec.version,
        "layer": {"id": layer.id, "label": layer.label},
        "skipped_layers": skipped,
        "median_years": median,
        "range_low_years": solve_time(s, 0.75),
        "range_high_years": solve_time(s, 0.25),
        "survival_at": {str(t): s(float(t)) for t in SURVIVAL_TIMES},
        "beyond_reliable": median is None or median > spec.max_reliable_years,
        "curve": [[k * CURVE_STEP_YEARS, s(k * CURVE_STEP_YEARS)] for k in range(steps + 1)],
        "inputs": [
            {
                "id": i.id,
                "label": i.label,
                "status": resolved.status[i.id] if i.id in used else "unused",
                "value": resolved.values.get(i.id),
                "assumed": [w.model_dump() for w in i.missing or []] if i.id in unknown else None,
            }
            for i in spec.inputs
        ],
        "terms": [
            {
                "input": t.input,
                "kind": t.kind,
                "contribution": (
                    term_value(t, resolved.values)
                    if all(n in resolved.values for n in term_inputs(t))
                    else None
                ),
            }
            for t in layer.survival.terms
        ],
    }
