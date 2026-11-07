/**
 * TypeScript mirror of src/backend/general/spec.py (the model-spec JSON contract).
 * The Python side validates every spec at export time, so the browser trusts this shape.
 */

export const SCHEMA_VERSION = 1;

export interface CodeSet {
  icd10: string[];
  icd9: string[];
  snomed: string[];
}

export type ExtractRule =
  | { rule: "age" }
  | { rule: "sex" }
  | { rule: "observation_number"; loinc: string[]; snomed: string[]; units: Record<string, number>; max_age_days: number | null }
  | { rule: "observation_coded"; loinc: string[]; snomed: string[]; values: Record<string, string>; max_age_days: number | null }
  | { rule: "condition_category"; categories: { value: Value; codes: CodeSet }[] }
  | { rule: "condition_present"; codes: CodeSet; admitted_within_days: number | null }
  | { rule: "condition_weighted_sum"; groups: { weight: number; codes: CodeSet }[] }
  | { rule: "years_since_condition"; codes: CodeSet }
  | { rule: "years_since_category"; categories: { value: Value; codes: CodeSet }[] }
  | { rule: "medication_present"; rxnorm: string[]; atc: string[]; names: string[] }
  | { rule: "first_of"; rules: ExtractRule[] };

export type Value = number | string | boolean;

export interface WeightedValue {
  value: Value;
  weight: number;
}

interface InputBase {
  id: string;
  label: string;
  extract: ExtractRule;
  /** null => required by every layer. [] => optional, used only by layers requiring it. */
  missing: WeightedValue[] | null;
  source: string | null;
}

export type Input =
  | (InputBase & { type: "number"; unit: string | null; min: number; max: number })
  | (InputBase & { type: "enum"; values: string[] })
  | (InputBase & { type: "boolean" });

export type Term =
  | { kind: "linear"; input: string; coef: number; center: number; min: number | null; max: number | null }
  | { kind: "bands"; input: string; bands: Band[] }
  | { kind: "category"; input: string; values: Record<string, number> }
  | { kind: "grid"; input: string; by: string; rows: { lt: number | null; bands: Band[] }[] };

export interface Band {
  lt: number | null;
  value: number;
}

export const termInputs = (t: Term): string[] => (t.kind === "grid" ? [t.input, t.by] : [t.input]);

export type Survival =
  | { type: "weibull_ph"; shape: number; scale_years: number; terms: Term[] }
  | { type: "life_table_ph"; life_table: string; age_input: string; sex_input: string; terms: Term[] }
  | {
      type: "relative_survival";
      life_table: string;
      age_input: string;
      sex_input: string;
      since_input: string;
      keys: string[];
      curves: RelativeSurvivalCurve[];
      terms: Term[];
    }
  | {
      type: "score_weibull";
      times: [number, number];
      survival: [number, number][];
      terms: Term[];
      life_table: string | null;
      age_input: string;
      sex_input: string;
    }
  | {
      type: "score_life_table";
      time: number;
      survival: number[];
      terms: Term[];
      life_table: string;
      age_input: string;
      sex_input: string;
    };

export type ScoreSurvival = Extract<Survival, { type: "score_weibull" | "score_life_table" }>;

/** Survival forms driven by an integer risk score (shown to the user as points). */
export function isScoreForm(survival: Survival): survival is ScoreSurvival {
  return survival.type === "score_weibull" || survival.type === "score_life_table";
}

export interface RelativeSurvivalCurve {
  match: Record<string, string>;
  age_lt: number | null;
  relative: number[];
  note: string;
}

interface LifeTable {
  source: string;
  label: string;
  female: number[];
  male: number[];
}

interface Layer {
  id: string;
  label: string;
  description: string;
  requires: string[];
  when: Record<string, Value[]>;
  survival: Survival;
  sources: string[];
}

export interface Source {
  id: string;
  citation: string;
  url: string;
  licence: string | null;
}

export interface ValidationResult {
  dataset: string;
  period: string;
  n: number;
  metric: string;
  value: number;
  notes: string;
  source: string | null;
}

export interface ModelSpec {
  schema_version: typeof SCHEMA_VERSION;
  id: string;
  name: string;
  version: string;
  order: number;
  description: string;
  group_codes: CodeSet;
  inputs: Input[];
  layers: Layer[];
  life_tables: Record<string, LifeTable>;
  max_reliable_years: number;
  validation: ValidationResult[];
  sources: Source[];
}

/** The name of the life table a layer's survival function reads, or null if it reads none. */
export function lifeTableOf(survival: Survival): string | null {
  return survival.type === "weibull_ph" ? null : survival.life_table;
}

/** Inputs a layer's survival function reads, in first-use order (the evaluation order). */
export function layerInputs(layer: Layer): string[] {
  const names: string[] = [];
  const s = layer.survival;
  if (s.type !== "weibull_ph" && s.life_table !== null) names.push(s.age_input, s.sex_input); // reads a life table
  if (s.type === "relative_survival") names.push(s.since_input, ...s.keys);
  for (const t of s.terms) names.push(...termInputs(t));
  return [...new Set(names)];
}
