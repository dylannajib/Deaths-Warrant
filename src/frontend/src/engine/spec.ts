/**
 * TypeScript mirror of src/backend/deaths_warrant/spec.py (the model-spec JSON contract).
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
  | { rule: "observation_number"; loinc: string[]; units: Record<string, number>; max_age_days: number | null }
  | { rule: "observation_coded"; loinc: string[]; values: Record<string, string>; max_age_days: number | null }
  | { rule: "condition_category"; categories: { value: string; codes: CodeSet }[] }
  | { rule: "condition_present"; codes: CodeSet }
  | { rule: "condition_weighted_sum"; groups: { weight: number; codes: CodeSet }[] }
  | { rule: "years_since_condition"; codes: CodeSet }
  | { rule: "medication_present"; rxnorm: string[]; atc: string[]; names: string[] };

export type Value = number | string | boolean;

export interface WeightedValue {
  value: Value;
  weight: number;
}

interface InputBase {
  id: string;
  label: string;
  extract: ExtractRule;
  missing: WeightedValue[] | null;
  source: string | null;
}

export type Input =
  | (InputBase & { type: "number"; unit: string | null; min: number; max: number })
  | (InputBase & { type: "enum"; values: string[] })
  | (InputBase & { type: "boolean" });

export type Term =
  | { kind: "linear"; input: string; coef: number; center: number; min: number | null; max: number | null }
  | { kind: "bands"; input: string; bands: { lt: number | null; value: number }[] }
  | { kind: "category"; input: string; values: Record<string, number> };

export type Survival =
  | { type: "weibull_ph"; shape: number; scale_years: number; terms: Term[] }
  | { type: "life_table_ph"; life_table: string; age_input: string; sex_input: string; terms: Term[] };

export interface LifeTable {
  source: string;
  female: number[];
  male: number[];
}

export interface Layer {
  id: string;
  label: string;
  description: string;
  requires: string[];
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

/** Inputs a layer's survival function reads, in first-use order (the evaluation order). */
export function layerInputs(layer: Layer): string[] {
  const names: string[] = [];
  if (layer.survival.type === "life_table_ph") names.push(layer.survival.age_input, layer.survival.sex_input);
  for (const t of layer.survival.terms) names.push(t.input);
  return [...new Set(names)];
}
