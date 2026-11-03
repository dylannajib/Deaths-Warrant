"""Accuracy metrics for validating models against real, censored survival data.

Pure Python so the pipeline needs no scientific stack. Inputs are parallel sequences:
``times`` (years of follow-up), ``events`` (True = died, False = censored) and model outputs.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import groupby
from typing import Any


def kaplan_meier(times: Sequence[float], events: Sequence[bool]) -> list[tuple[float, float]]:
    """Kaplan–Meier survival estimate as (time, S(time)) steps at each event time."""
    data = sorted(zip(times, events, strict=True))
    at_risk = len(data)
    s = 1.0
    steps: list[tuple[float, float]] = []
    for t, group in groupby(data, key=lambda d: d[0]):
        rows = list(group)
        deaths = sum(1 for _, e in rows if e)
        if deaths:
            s *= 1 - deaths / at_risk
            steps.append((t, s))
        at_risk -= len(rows)
    return steps


def km_at(steps: list[tuple[float, float]], t: float) -> float:
    s = 1.0
    for time, value in steps:
        if time > t:
            break
        s = value
    return s


def km_median(steps: list[tuple[float, float]]) -> float | None:
    return next((t for t, s in steps if s <= 0.5), None)


def harrell_c(times: Sequence[float], events: Sequence[bool], predicted: Sequence[float]) -> float:
    """Harrell's C: P(shorter predicted survival | shorter observed survival), O(n log n).

    ``predicted`` is any score where larger means longer expected survival (e.g. median years).
    Ties in prediction count one half.
    """
    ranks = {v: k + 1 for k, v in enumerate(sorted(set(predicted)))}
    tree = [0] * (len(ranks) + 1)

    def add(r: int) -> None:
        while r < len(tree):
            tree[r] += 1
            r += r & -r

    def count_le(r: int) -> int:
        n = 0
        while r > 0:
            n += tree[r]
            r -= r & -r
        return n

    order = sorted(range(len(times)), key=lambda i: times[i], reverse=True)
    inserted = concordant = discordant = tied = 0
    for _, group in groupby(order, key=lambda i: times[i]):
        members = list(group)
        for i in members:  # compare with everyone who survived strictly longer
            if events[i]:
                r = ranks[predicted[i]]
                less, le = count_le(r - 1), count_le(r)
                discordant += less
                tied += le - less
                concordant += inserted - le
        for i in members:
            add(ranks[predicted[i]])
        inserted += len(members)
    usable = concordant + discordant + tied
    if usable == 0:
        raise ValueError("no comparable pairs")
    return (concordant + 0.5 * tied) / usable


def calibration_at(
    t: float, times: Sequence[float], events: Sequence[bool], predicted_survival: Sequence[float]
) -> tuple[float, float]:
    """(mean predicted S(t), observed Kaplan–Meier S(t)) for the cohort."""
    observed = km_at(kaplan_meier(times, events), t)
    return sum(predicted_survival) / len(predicted_survival), observed


def result_row(
    dataset: str, period: str, n: int, metric: str, value: float, notes: str, source: str
) -> dict[str, Any]:
    """One aggregate result as written to a model's validation file."""
    return {
        "dataset": dataset,
        "period": period,
        "n": n,
        "metric": metric,
        "value": round(value, 3),
        "notes": notes,
        "source": source,
    }
