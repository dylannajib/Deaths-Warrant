"""Shared fixtures."""

from __future__ import annotations

import pytest

from general.registry import load_model
from general.spec import ModelSpec

FIXTURE = load_model("_fixture")
FIXTURE_SPEC = FIXTURE.FIXTURE_SPEC


@pytest.fixture
def spec() -> ModelSpec:
    return FIXTURE.build()
