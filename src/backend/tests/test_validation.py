import itertools
import random

import pytest

from deaths_warrant.validation import calibration_at, harrell_c, kaplan_meier, km_at, km_median


def naive_c(times, events, predicted):
    conc = disc = tied = 0
    for i, j in itertools.permutations(range(len(times)), 2):
        if events[i] and times[i] < times[j]:
            if predicted[i] < predicted[j]:
                conc += 1
            elif predicted[i] > predicted[j]:
                disc += 1
            else:
                tied += 1
    return (conc + 0.5 * tied) / (conc + disc + tied)


def test_kaplan_meier_textbook_example():
    # deaths at 1 and 3, censored at 2 and 4
    steps = kaplan_meier([1, 2, 3, 4], [True, False, True, False])
    assert steps == [(1, 0.75), (3, 0.375)]
    assert km_at(steps, 2.5) == 0.75
    assert km_median(steps) == 3


def test_harrell_c_matches_naive_with_ties():
    rng = random.Random(7)  # noqa: S311 - deterministic test data
    times = [rng.choice([1, 2, 3, 4, 5]) for _ in range(60)]
    events = [rng.random() < 0.6 for _ in range(60)]
    predicted = [rng.choice([1.0, 2.0, 3.0]) for _ in range(60)]
    assert harrell_c(times, events, predicted) == pytest.approx(naive_c(times, events, predicted))


def test_harrell_c_perfect_ordering():
    assert harrell_c([1, 2, 3], [True, True, True], [10, 20, 30]) == 1.0


def test_calibration_at():
    predicted, observed = calibration_at(2.5, [1, 2, 3, 4], [True, False, True, False], [0.7, 0.8])
    assert predicted == pytest.approx(0.75)
    assert observed == 0.75
