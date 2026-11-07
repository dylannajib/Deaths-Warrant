"""The model spec: the JSON contract between the Python pipeline and the browser evaluator.

Every model is exported as one self-contained ``spec.json`` validated by ``ModelSpec``.
The TypeScript mirror lives in ``src/frontend/engine/spec.ts``. Keep both in sync and
bump ``SCHEMA_VERSION`` on any breaking change.
"""

from __future__ import annotations

import itertools
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1
MAX_MISSING_COMBINATIONS = 65536


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- code sets


class CodeSet(_Strict):
    """Clinical codes. ICD codes match by prefix (dots ignored), SNOMED/LOINC/RxNorm exactly."""

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


Value = float | str | bool

# ---------------------------------------------------------------- extraction rules
# How the browser turns a parsed patient record into an input value.


class AgeRule(_Strict):
    rule: Literal["age"] = "age"


class SexRule(_Strict):
    rule: Literal["sex"] = "sex"


def _require_code(rule: ObservationNumberRule | ObservationCodedRule) -> None:
    if not rule.loinc and not rule.snomed:
        raise ValueError("an observation rule needs LOINC or SNOMED codes")


class ObservationNumberRule(_Strict):
    """Latest numeric observation with one of the LOINC codes, converted to the canonical unit.

    ``units`` maps a lower-cased UCUM/display unit to the multiplier into the canonical unit.
    The key ``""`` covers observations recorded without a unit.
    """

    rule: Literal["observation_number"] = "observation_number"
    loinc: list[str] = []
    snomed: list[str] = []  # for scales without a LOINC code (e.g. mMRC dyspnoea)
    units: dict[str, float] = Field(min_length=1)
    max_age_days: int | None = None

    @model_validator(mode="after")
    def _has_code(self) -> ObservationNumberRule:
        _require_code(self)
        return self


class ObservationCodedRule(_Strict):
    """Latest coded observation.

    ``values`` maps ``"system:code"`` (e.g. ``"snomed:258219007"``) or ``"text:<lower-case
    display text>"`` to an enum value.
    """

    rule: Literal["observation_coded"] = "observation_coded"
    loinc: list[str] = []
    snomed: list[str] = []
    values: dict[str, str] = Field(min_length=1)
    max_age_days: int | None = None

    @model_validator(mode="after")
    def _has_code(self) -> ObservationCodedRule:
        _require_code(self)
        return self


class Category(_Strict):
    value: Value
    codes: CodeSet


class ConditionCategoryRule(_Strict):
    """First category (in listed order, i.e. priority) matched by any recorded condition."""

    rule: Literal["condition_category"] = "condition_category"
    categories: list[Category] = Field(min_length=1)


class ConditionPresentRule(_Strict):
    """True if any matching condition is recorded. An unrecorded condition counts as absent.

    With ``admitted_within_days``, only a diagnosis recorded during a hospital stay that began
    within that many days before the as-of date counts (e.g. a recent heart-failure admission).
    """

    rule: Literal["condition_present"] = "condition_present"
    codes: CodeSet
    admitted_within_days: int | None = Field(default=None, ge=1)


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


class YearsSinceCategoryRule(_Strict):
    """Years since the earliest dated condition in the first category the record matches.

    Uses the same priority as ``condition_category``, so with several primary cancers the time
    since diagnosis belongs to the cancer the model is using.
    """

    rule: Literal["years_since_category"] = "years_since_category"
    categories: list[Category] = Field(min_length=1)


class FirstOfRule(_Strict):
    """The first of ``rules`` (in priority order) that yields a value."""

    rule: Literal["first_of"] = "first_of"
    rules: list[ExtractRule] = Field(min_length=2)


class MedicationPresentRule(_Strict):
    """True if any matching medication is recorded (RxNorm exact, ATC prefix, name substring).

    Unknown (missing) when the record contains no medications at all.
    """

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
    | YearsSinceCategoryRule
    | MedicationPresentRule
    | FirstOfRule,
    Field(discriminator="rule"),
]
FirstOfRule.model_rebuild()


# ---------------------------------------------------------------- inputs


class WeightedValue(_Strict):
    value: Value
    weight: float = Field(gt=0)


class _InputBase(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    extract: ExtractRule
    # Population distribution used when the record lacks this input. None => required by
    # every layer. [] => optional, usable only by layers that require it.
    missing: list[WeightedValue] | None = None
    source: str | None = None  # Source id backing the missing-value distribution


class NumberInput(_InputBase):
    type: Literal["number"] = "number"
    unit: str | None = None
    # Values outside [min, max] are treated as implausible and ignored.
    min: float
    max: float

    def accepts(self, v: Value) -> bool:
        """A plausible value: a finite number within [min, max]."""
        return (
            isinstance(v, int | float)
            and not isinstance(v, bool)
            and math.isfinite(v)
            and self.min <= v <= self.max
        )


class EnumInput(_InputBase):
    type: Literal["enum"] = "enum"
    values: list[str] = Field(min_length=2)

    def accepts(self, v: Value) -> bool:
        return v in self.values


class BooleanInput(_InputBase):
    type: Literal["boolean"] = "boolean"

    def accepts(self, v: Value) -> bool:
        return isinstance(v, bool)


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
    lt: float | None  # upper bound (exclusive), None = catch-all, must be last
    value: float


def _check_catch_all(bands: list[Band] | list[GridRow]) -> None:
    if bands[-1].lt is not None or any(b.lt is None for b in bands[:-1]):
        raise ValueError("only the last band, and it must, have lt=null")


class BandsTerm(_Strict):
    """Value of the first band with x < lt."""

    kind: Literal["bands"] = "bands"
    input: str
    bands: list[Band] = Field(min_length=1)

    @model_validator(mode="after")
    def _last_is_catch_all(self) -> BandsTerm:
        _check_catch_all(self.bands)
        return self


class GridRow(_Strict):
    lt: float | None  # upper bound on the row input (exclusive), None = catch-all, last
    bands: list[Band] = Field(min_length=1)  # bands of the ``by`` input

    @model_validator(mode="after")
    def _last_is_catch_all(self) -> GridRow:
        _check_catch_all(self.bands)
        return self


class GridTerm(_Strict):
    """Two-way interaction: the first row with input < lt, then that row's band for ``by``.

    E.g. MAGGIC's age points depend on the ejection-fraction band.
    """

    kind: Literal["grid"] = "grid"
    input: str
    by: str
    rows: list[GridRow] = Field(min_length=1)

    @model_validator(mode="after")
    def _last_is_catch_all(self) -> GridTerm:
        _check_catch_all(self.rows)
        return self


class CategoryTerm(_Strict):
    """Coefficient per category. Booleans use the keys "true"/"false"."""

    kind: Literal["category"] = "category"
    input: str
    values: dict[str, float]


Term = Annotated[LinearTerm | BandsTerm | CategoryTerm | GridTerm, Field(discriminator="kind")]


def term_inputs(term: LinearTerm | BandsTerm | CategoryTerm | GridTerm) -> list[str]:
    return [term.input, term.by] if isinstance(term, GridTerm) else [term.input]


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


class RelativeSurvivalCurve(_Strict):
    """Published relative survival R(k) at whole years k = 1..n since diagnosis (R(0) = 1).

    ``match`` selects the curve by enum inputs, and ``age_lt`` bounds the age at diagnosis
    (exclusive, None = any age). The first matching curve is used.
    """

    match: dict[str, str]
    age_lt: float | None = None
    relative: list[float] = Field(min_length=1)
    note: str = ""

    @model_validator(mode="after")
    def _non_increasing(self) -> RelativeSurvivalCurve:
        prev = 1.0
        for r in self.relative:
            if not 0 < r <= prev:
                raise ValueError("relative survival must be in (0, 1] and non-increasing")
            prev = r
        return self


class RelativeSurvival(_Strict):
    """Net (relative) survival on top of population mortality, conditional on survival so far.

    With d years since diagnosis and excess cumulative hazard X(t) = -ln R(t) (linear between
    whole years, last slope continued): S(t) = S_pop(age, t) * exp(-exp(lp) * (X(d+t) - X(d))).
    The curve is chosen by the age at diagnosis, age - d.
    """

    type: Literal["relative_survival"] = "relative_survival"
    life_table: str
    age_input: str = "age"
    sex_input: str = "sex"
    since_input: str
    keys: list[str] = []  # enum inputs that every curve's ``match`` uses
    curves: list[RelativeSurvivalCurve] = Field(min_length=1)
    terms: list[Term] = []  # multiply the excess hazard

    @model_validator(mode="after")
    def _keys(self) -> RelativeSurvival:
        for c in self.curves:
            if list(c.match) != self.keys:
                raise ValueError(f"curve match {c.match} must use exactly the keys {self.keys}")
        return self


class ScoreWeibull(_Strict):
    """A published integer risk score and its survival at two times (e.g. MAGGIC at 1 and 3 y).

    score = sum of the term values, rounded and clamped to the table. Each score's two published
    points are joined by a Weibull, H(t) = H1 * (t / t1) ** k with H1 = -ln S(t1) and
    k = ln(ln S(t2) / ln S(t1)) / ln(t2 / t1), which also extends it beyond t2. With a life
    table, survival is never better than the general population of the same age and sex.
    """

    type: Literal["score_weibull"] = "score_weibull"
    times: list[float] = Field(min_length=2, max_length=2)
    survival: list[list[float]] = Field(min_length=2)  # row k = score k: [S(t1), S(t2)]
    terms: list[Term] = Field(min_length=1)
    life_table: str | None = None
    age_input: str = "age"
    sex_input: str = "sex"

    @model_validator(mode="after")
    def _table(self) -> ScoreWeibull:
        if not 0 < self.times[0] < self.times[1]:
            raise ValueError("score times must be positive and increasing")
        for row in self.survival:
            if len(row) != 2 or not 1 > row[0] > row[1] > 0:
                raise ValueError("each score row must be [S(t1), S(t2)] with 1 > S(t1) > S(t2) > 0")
        return self


class ScoreLifeTable(_Strict):
    """A published integer risk score with survival at one time (e.g. ADO at 3 years).

    The score's published S(t1) sets a hazard ratio on the patient's own population mortality,
    HR = -ln S(t1) / H_pop(age, t1), floored at 1 (never better than the population), so the
    curve follows normal ageing and passes through the published point.
    """

    type: Literal["score_life_table"] = "score_life_table"
    time: float = Field(gt=0)
    survival: list[float] = Field(min_length=2)  # index k = score k: S(time)
    terms: list[Term] = Field(min_length=1)
    life_table: str
    age_input: str = "age"
    sex_input: str = "sex"

    @model_validator(mode="after")
    def _table(self) -> ScoreLifeTable:
        if not all(0 < x < 1 for x in self.survival):
            raise ValueError("score survival values must be in (0, 1)")
        return self


Survival = Annotated[
    WeibullPH | LifeTablePH | RelativeSurvival | ScoreWeibull | ScoreLifeTable,
    Field(discriminator="type"),
]


# Survival forms built on population mortality: each has life_table, age_input and sex_input.
PopulationForm = LifeTablePH | RelativeSurvival | ScoreWeibull | ScoreLifeTable


def life_table_of(survival: Survival) -> str | None:
    """The life table a survival form reads (with its age and sex inputs), if any."""
    return survival.life_table if isinstance(survival, PopulationForm) else None


class LifeTable(_Strict):
    """Annual probability of death q(x) for integer ages 0..len-1. The last age repeats."""

    source: str
    label: str  # shown to the user, e.g. "United States life tables, 2024"
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
    # Inputs that must be observed with one of the listed values (e.g. diagnosis = heart failure)
    when: dict[str, list[Value]] = {}
    survival: Survival
    sources: list[str] = []


# ---------------------------------------------------------------- provenance


class Source(_Strict):
    id: str
    citation: str
    url: str = Field(pattern=r"^https://[^\s]+$")  # rendered as a link in the app
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
    group_codes: CodeSet  # a record with none of these codes is refused for this group
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
        if self.layers[-1].when:
            raise ValueError("the last layer must have no `when` conditions")
        for layer in self.layers:
            used = layer_inputs(layer)
            needed = layer_needs(layer)
            for name in [*used, *needed]:
                if name not in inputs:
                    raise ValueError(f"layer {layer.id!r} references unknown input {name!r}")
            for name, allowed in layer.when.items():
                for v in allowed:
                    _check_value(inputs[name], v, f"layer {layer.id!r} `when`")
            table = life_table_of(layer.survival)
            if table is not None:
                if table not in self.life_tables:
                    raise ValueError(f"layer {layer.id!r} references unknown life table")
                sex = inputs[layer.survival.sex_input]
                if not isinstance(sex, EnumInput) or set(sex.values) != {"female", "male"}:
                    raise ValueError("life-table sex input must be an enum of female/male")
                if not isinstance(inputs[layer.survival.age_input], NumberInput):
                    raise ValueError("life-table age input must be a number")
            if isinstance(layer.survival, RelativeSurvival):
                _check_curves(layer.survival, inputs)
            for term in layer.survival.terms:
                _check_term(term, inputs)
            for name in used:
                if name not in needed and inputs[name].missing == []:
                    raise ValueError(
                        f"layer {layer.id!r} uses {name!r}, which has no missing-value"
                        " distribution, without requiring it"
                    )
            combos = math.prod(len(inputs[n].missing or [None]) for n in used if n not in needed)
            if combos > MAX_MISSING_COMBINATIONS:
                raise ValueError(f"layer {layer.id!r} has {combos} missing-value combinations")
        for i in self.inputs:
            for wv in i.missing or []:
                _check_value(i, wv.value, "missing-distribution")
        return self


def layer_inputs(layer: Layer) -> list[str]:
    """Inputs a layer's survival function reads, in first-use order (the evaluation order)."""
    names: list[str] = []
    survival = layer.survival
    if life_table_of(survival) is not None:
        assert isinstance(survival, PopulationForm)
        names += [survival.age_input, survival.sex_input]
    if isinstance(survival, RelativeSurvival):
        names += [survival.since_input, *survival.keys]
    for t in survival.terms:
        names += term_inputs(t)
    return list(dict.fromkeys(names))


def layer_needs(layer: Layer) -> list[str]:
    """Inputs that must be observed for the layer to apply (never marginalised)."""
    return list(dict.fromkeys([*layer.requires, *layer.when]))


def _check_curves(survival: RelativeSurvival, inputs: dict[str, Input]) -> None:
    if not isinstance(inputs[survival.since_input], NumberInput):
        raise ValueError("relative-survival since input must be a number")
    domains: dict[str, list[str]] = {}
    for key in survival.keys:
        i = inputs[key]
        if not isinstance(i, EnumInput):
            raise ValueError(f"relative-survival key {key!r} must be an enum input")
        domains[key] = i.values
    for c in survival.curves:
        for key, value in c.match.items():
            if value not in domains[key]:
                raise ValueError(f"curve matches unknown {key} value {value!r}")
    covered = {tuple(c.match.values()) for c in survival.curves if c.age_lt is None}
    for combo in itertools.product(*domains.values()):
        if combo not in covered:
            raise ValueError(f"no all-ages relative-survival curve for {combo}")


def _check_term(term: Term, inputs: dict[str, Input]) -> None:
    i = inputs[term.input]
    if isinstance(term, GridTerm):
        if not isinstance(i, NumberInput) or not isinstance(inputs[term.by], NumberInput):
            raise ValueError(f"grid term on {term.input!r} x {term.by!r} needs number inputs")
        return
    if isinstance(term, CategoryTerm):
        expected = set(i.values) if isinstance(i, EnumInput) else {"true", "false"}
        if isinstance(i, NumberInput) or set(term.values) != expected:
            raise ValueError(f"category term on {i.id!r} must cover exactly {sorted(expected)}")
    elif not isinstance(i, NumberInput):
        raise ValueError(f"{term.kind} term needs a number input, {i.id!r} is {i.type}")


def _check_value(i: NumberInput | EnumInput | BooleanInput, v: Value, where: str) -> None:
    if not i.accepts(v):
        raise ValueError(f"input {i.id!r}: {where} value {v!r} is not a valid value")
