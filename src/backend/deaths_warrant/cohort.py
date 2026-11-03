"""Predictions for a described cohort, used by the validation scripts against published results.

Kept apart from ``validation.py`` (pure statistics) because these helpers run the model.
"""

from __future__ import annotations

from typing import Any

from .evaluate import evaluate
from .spec import ModelSpec


def curve_at(result: dict[str, Any], t: float) -> float:
    """S(t) read from an evaluation result's curve; t must lie on the curve's time grid."""
    step = result["curve"][1][0]
    k = round(t / step)
    if abs(k * step - t) > 1e-9:
        raise ValueError(f"t = {t} is not on the {step}-year curve grid")
    return result["curve"][k][1]


def sex_mix(spec: ModelSpec, observed: dict[str, Any], male: float, t: float) -> float:
    """Survival at t for a cohort with the given male share, otherwise the same inputs."""
    return sum(
        w * curve_at(evaluate(spec, {**observed, "sex": sex}), t)
        for sex, w in (("male", male), ("female", 1 - male))
    )
