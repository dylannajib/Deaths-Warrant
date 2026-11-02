"""The model spec: the JSON contract between the Python pipeline and the browser evaluator.

Every model is exported as one self-contained ``spec.json`` validated by ``ModelSpec``.
The TypeScript mirror lives in ``src/frontend/src/engine/spec.ts``; keep both in sync and
bump ``SCHEMA_VERSION`` on any breaking change.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1
MAX_MISSING_COMBINATIONS = 4096


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- code sets


class CodeSet(_Strict):
    """Clinical codes. ICD codes match by prefix (dots ignored); SNOMED/LOINC/RxNorm exactly."""

    icd10: list[str] = []
    icd9: list[str] = []
    snomed: list[str] = []

    @model_validator(mode="after")
    def _normalise(self) -> CodeSet:
        for icd in (self.icd10, self.icd9):
            for code in icd:
                if code != code.upper().replace(".", ""):
                    raise ValueError(f"ICD prefix {code!r} must be upper-case without dots")
        return self


# ---------------------------------------------------------------- extraction rules
# How the browser turns a parsed patient record into an input value.


class AgeRule(_Strict):
    rule: Literal["age"] = "age"


class SexRule(_Strict):
    rule: Literal["sex"] = "sex"


class ObservationNumberRule(_Strict):
    """Latest numeric observation with one of the LOINC codes, converted to the canonical unit.

    ``units`` maps a lower-cased UCUM/display unit to the multiplier into the canonical unit.
    The key ``""`` covers observations recorded without a unit.
    """

    rule: Literal["observation_number"] = "observation_number"
    loinc: list[str] = Field(min_length=1)
    units: dict[str, float] = Field(min_length=1)
    max_age_days: int | None = None


class ObservationCodedRule(_Strict):
    """Latest coded observation.

    ``values`` maps ``"system:code"`` (e.g. ``"snomed:258219007"``) or ``"text:<lower-case
    display text>"`` to an enum value.
    """

    rule: Literal["observation_coded"] = "observation_coded"
    loinc: list[str] = Field(min_length=1)
    values: dict[str, str] = Field(min_length=1)
    max_age_days: int | None = None


class Category(_Strict):
    value: str
    codes: CodeSet


class ConditionCategoryRule(_Strict):
    """First category (in listed order, i.e. priority) matched by any recorded condition."""

    rule: Literal["condition_category"] = "condition_category"
    categories: list[Category] = Field(min_length=1)


class ConditionPresentRule(_Strict):
    """True if any matching condition is recorded; an unrecorded condition counts as absent."""

    rule: Literal["condition_present"] = "condition_present"
    codes: CodeSet


class WeightedGroup(_Strict):
    weight: float
    codes: CodeSet


class ConditionWeightedSumRule(_Strict):
    """Sum of weights of the groups with at least one recorded condition (e.g. Charlson)."""

    rule: Literal["condition_weighted_sum"] = "condition_weighted_sum"
    groups: list[WeightedGroup] = Field(min_length=1)


class YearsSinceConditionRule(_Strict):
    """Years since the earliest dated matching condition."""

    rule: Literal["years_since_condition"] = "years_since_condition"
    codes: CodeSet


class MedicationPresentRule(_Strict):
    """True if any matching medication is recorded (RxNorm exact, ATC prefix, name substring)."""

    rule: Literal["medication_present"] = "medication_present"
    rxnorm: list[str] = []
    atc: list[str] = []
    names: list[str] = []


ExtractRule = Annotated[
    AgeRule
    | SexRule
    | ObservationNumberRule
    | ObservationCodedRule
    | ConditionCategoryRule
    | ConditionPresentRule
    | ConditionWeightedSumRule
    | YearsSinceConditionRule
    | MedicationPresentRule,
    Field(discriminator="rule"),
]


# ---------------------------------------------------------------- inputs

Value = float | str | bool


class WeightedValue(_Strict):
    value: Value
    weight: float = Field(gt=0)


class _InputBase(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    extract: ExtractRule
    # Population distribution used when the record lacks this input. None => required.
    missing: list[WeightedValue] | None = None
    source: str | None = None  # Source id backing the missing-value distribution


class NumberInput(_InputBase):
    type: Literal["number"] = "number"
    unit: str | None = None
    # Values outside [min, max] are treated as implausible and ignored.
    min: float
    max: float


class EnumInput(_InputBase):
    type: Literal["enum"] = "enum"
    values: list[str] = Field(min_length=2)


class BooleanInput(_InputBase):
    type: Literal["boolean"] = "boolean"


Input = Annotated[NumberInput | EnumInput | BooleanInput, Field(discriminator="type")]


# ---------------------------------------------------------------- linear-predictor terms


class LinearTerm(_Strict):
    """coef * (clamp(x, min, max) - center)."""

    kind: Literal["linear"] = "linear"
    input: str
    coef: float
    center: float = 0.0
    min: float | None = None
    max: float | None = None


class Band(_Strict):
    lt: float | None  # upper bound (exclusive); None = catch-all, must be last
    value: float


class BandsTerm(_Strict):
    """Value of the first band with x < lt."""

    kind: Literal["bands"] = "bands"
    input: str
    bands: list[Band] = Field(min_length=1)

    @model_validator(mode="after")
    def _last_is_catch_all(self) -> BandsTerm:
        if self.bands[-1].lt is not None or any(b.lt is None for b in self.bands[:-1]):
            raise ValueError("only the last band, and it must, have lt=null")
        return self


class CategoryTerm(_Strict):
    """Coefficient per category; booleans use the keys "true"/"false"."""

    kind: Literal["category"] = "category"
    input: str
    values: dict[str, float]


Term = Annotated[LinearTerm | BandsTerm | CategoryTerm, Field(discriminator="kind")]


# ---------------------------------------------------------------- survival functions


class WeibullPH(_Strict):
    """Proportional-hazards Weibull: H(t) = exp(lp) * (t / scale_years) ** shape."""

    type: Literal["weibull_ph"] = "weibull_ph"
    shape: float = Field(gt=0)
    scale_years: float = Field(gt=0)
    terms: list[Term] = []


class LifeTablePH(_Strict):
    """Background population mortality scaled by a hazard ratio: H(t) = exp(lp) * H_pop(t)."""

    type: Literal["life_table_ph"] = "life_table_ph"
    life_table: str
    age_input: str = "age"
    sex_input: str = "sex"
    terms: list[Term] = []


Survival = Annotated[WeibullPH | LifeTablePH, Field(discriminator="type")]


class LifeTable(_Strict):
    """Annual probability of death q(x) for integer ages 0..len-1; the last age repeats."""

    source: str
    female: list[float] = Field(min_length=2)
    male: list[float] = Field(min_length=2)

    @model_validator(mode="after")
    def _probabilities(self) -> LifeTable:
        for q in (*self.female, *self.male):
            if not 0 <= q < 1:
                raise ValueError("q(x) must be in [0, 1)")
        return self


class Layer(_Strict):
    id: str
    label: str
    description: str
    requires: list[str] = []  # inputs that must be observed (not marginalised) to use this layer
    survival: Survival
    sources: list[str] = []


# ---------------------------------------------------------------- provenance


class Source(_Strict):
    id: str
    citation: str
    url: str
    licence: str | None = None


class ValidationResult(_Strict):
    dataset: str
    period: str
    n: int = Field(ge=20)  # never publish groups smaller than 20
    metric: str
    value: float
    notes: str = ""
    source: str | None = None


class ModelSpec(_Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    version: str
    order: int = 100  # position in the disease-group picker
    description: str
    group_codes: CodeSet  # used to warn when the record does not match the chosen group
    inputs: list[Input]
    layers: list[Layer] = Field(min_length=1)
    life_tables: dict[str, LifeTable] = {}
    max_reliable_years: float = 20.0
    validation: list[ValidationResult] = []
    sources: list[Source] = []

    @model_validator(mode="after")
    def _references(self) -> ModelSpec:
        inputs = {i.id: i for i in self.inputs}
        if len(inputs) != len(self.inputs):
            raise ValueError("duplicate input ids")
        source_ids = {s.id for s in self.sources}
        refs = [s for layer in self.layers for s in layer.sources]
        refs += [i.source for i in self.inputs if i.source]
        refs += [v.source for v in self.validation if v.source]
        for ref in refs:
            if ref not in source_ids:
                raise ValueError(f"unknown source {ref!r}")
        if self.layers[-1].requires:
            raise ValueError(
                "the last layer must have no requirements (every record needs a result)"
            )
        for layer in self.layers:
            used = layer_inputs(layer)
            for name in [*used, *layer.requires]:
                if name not in inputs:
                    raise ValueError(f"layer {layer.id!r} references unknown input {name!r}")
            if isinstance(layer.survival, LifeTablePH):
                if layer.survival.life_table not in self.life_tables:
                    raise ValueError(f"layer {layer.id!r} references unknown life table")
                sex = inputs[layer.survival.sex_input]
                if not isinstance(sex, EnumInput) or set(sex.values) != {"female", "male"}:
                    raise ValueError("life-table sex input must be an enum of female/male")
                if not isinstance(inputs[layer.survival.age_input], NumberInput):
                    raise ValueError("life-table age input must be a number")
            for term in layer.survival.terms:
                _check_term(term, inputs[term.input])
            combos = math.prod(
                len(inputs[n].missing or [None]) for n in used if n not in layer.requires
            )
            if combos > MAX_MISSING_COMBINATIONS:
                raise ValueError(f"layer {layer.id!r} has {combos} missing-value combinations")
        for i in self.inputs:
            _check_values(i)
        return self


def layer_inputs(layer: Layer) -> list[str]:
    """Inputs a layer's survival function reads, in first-use order (the evaluation order)."""
    names: list[str] = []
    if isinstance(layer.survival, LifeTablePH):
        names += [layer.survival.age_input, layer.survival.sex_input]
    names += [t.input for t in layer.survival.terms]
    return list(dict.fromkeys(names))


def _check_term(term: LinearTerm | BandsTerm | CategoryTerm, i: Input) -> None:
    if isinstance(term, CategoryTerm):
        expected = set(i.values) if isinstance(i, EnumInput) else {"true", "false"}
        if isinstance(i, NumberInput) or set(term.values) != expected:
            raise ValueError(f"category term on {i.id!r} must cover exactly {sorted(expected)}")
    elif not isinstance(i, NumberInput):
        raise ValueError(f"{term.kind} term needs a number input, {i.id!r} is {i.type}")


def _check_values(i: NumberInput | EnumInput | BooleanInput) -> None:
    for wv in i.missing or []:
        v = wv.value
        ok = (
            (isinstance(i, NumberInput) and isinstance(v, int | float) and not isinstance(v, bool))
            or (isinstance(i, EnumInput) and v in i.values)
            or (isinstance(i, BooleanInput) and isinstance(v, bool))
        )
        if not ok:
            raise ValueError(f"input {i.id!r}: missing-distribution value {v!r} has the wrong type")
