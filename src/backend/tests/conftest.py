"""Shared fixtures."""

from __future__ import annotations

import pytest

from deaths_warrant.registry import MODELS_DIR, ModelFolder
from deaths_warrant.spec import ModelSpec

FIXTURE = ModelFolder("_fixture", MODELS_DIR / "_fixture").load()
FIXTURE_SPEC = FIXTURE.FIXTURE_SPEC


@pytest.fixture
def spec() -> ModelSpec:
    return FIXTURE.build()
