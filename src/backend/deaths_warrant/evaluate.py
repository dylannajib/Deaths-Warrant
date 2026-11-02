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
    EnumInput,
    Input,
    LifeTable,
    LifeTablePH,
    LinearTerm,
    ModelSpec,
    NumberInput,
    Term,
    Value,
    WeibullPH,
    layer_inputs,
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
        elif _plausible(i, v):
            values[i.id] = v
            status[i.id] = "observed"
        else:
            status[i.id] = "implausible"
        if i.id not in values and i.missing is None:
            raise EvaluationError(f"{i.label} is required but was not found in the record")
    return _Resolved(values, status)


def _plausible(i: Input, v: Value) -> bool:
    if isinstance(i, NumberInput):
        return (
            isinstance(v, int | float)
            and not isinstance(v, bool)
            and math.isfinite(v)
            and i.min <= v <= i.max
        )
    if isinstance(i, EnumInput):
        return v in i.values
    return isinstance(v, bool)


def term_value(term: Term, x: Value) -> float:
    if isinstance(term, LinearTerm):
        xf = float(x)
        if term.min is not None:
            xf = max(xf, term.min)
        if term.max is not None:
            xf = min(xf, term.max)
        return term.coef * (xf - term.center)
    if isinstance(term, BandsTerm):
        for band in term.bands:
            if band.lt is None or float(x) < band.lt:
                return band.value
        raise AssertionError("unreachable: last band is a catch-all")
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


def _survival_fn(spec: ModelSpec, layer_index: int, values: Mapping[str, Value]) -> SurvivalFn:
    survival = spec.layers[layer_index].survival
    lp = 0.0
    for term in survival.terms:
        lp += term_value(term, values[term.input])
    hr = math.exp(lp)
    if isinstance(survival, WeibullPH):
        shape, scale = survival.shape, survival.scale_years
        return lambda t: math.exp(-hr * (t / scale) ** shape)
    assert isinstance(survival, LifeTablePH)
    table: LifeTable = spec.life_tables[survival.life_table]
    q = table.female if values[survival.sex_input] == "female" else table.male
    age = float(values[survival.age_input])
    return lambda t: math.exp(-hr * population_cum_hazard(q, age, t))


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


def evaluate(spec: ModelSpec, observed: Observed) -> dict[str, Any]:
    resolved = resolve_inputs(spec, observed)
    skipped = []
    layer_index = 0
    for layer_index, layer in enumerate(spec.layers):  # noqa: B007 - used after the loop
        lacking = [r for r in layer.requires if r not in resolved.values]
        if not lacking:
            break
        skipped.append({"id": layer.id, "label": layer.label, "lacking": lacking})
    layer = spec.layers[layer_index]
    inputs = {i.id: i for i in spec.inputs}
    used = layer_inputs(layer)
    unknown = [n for n in used if n not in resolved.values]

    fns: list[SurvivalFn] = []
    weights: list[float] = []
    for combo in itertools.product(*(inputs[n].missing or [] for n in unknown)):
        values = dict(resolved.values)
        weight = 1.0
        for name, wv in zip(unknown, combo, strict=True):
            values[name] = wv.value
            weight *= wv.weight
        fns.append(_survival_fn(spec, layer_index, values))
        weights.append(weight)
    total_weight = sum(weights)

    def s(t: float) -> float:
        acc = 0.0
        for fn, w in zip(fns, weights, strict=True):
            acc += w * fn(t)
        return acc / total_weight

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
                    term_value(t, resolved.values[t.input]) if t.input in resolved.values else None
                ),
            }
            for t in layer.survival.terms
        ],
    }
