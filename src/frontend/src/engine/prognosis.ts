/** The whole client-side pipeline: uploaded text → parsed record → inputs → prognosis. */

import { yearsBetween } from "../parsing/dates";
import type { SourceFormat } from "../parsing/record";
import { latestDate, parseUpload } from "../parsing/upload";
import { evaluate, type EvaluationResult } from "./evaluate";
import { extractInputs, recordMatchesGroup } from "./extract";
import { isScoreForm, type ModelSpec, type Source, type ValidationResult } from "./spec";

export const STALE_AFTER_YEARS = 1;

/** The parts of the spec the Reasoning panel shows (the page never loads the full spec). */
export interface ReportModel {
  id: string;
  name: string;
  version: string;
  description: string;
  max_reliable_years: number;
  layer: { label: string; description: string; sources: string[]; kind: "points" | "hazard" };
  inputs: Record<string, { label: string; unit: string | null; source: string | null }>;
  sources: Source[];
  validation: ValidationResult[];
}

export interface PrognosisReport {
  format: SourceFormat;
  asOf: string;
  model: ReportModel;
  result: EvaluationResult;
  provenance: Record<string, string>;
  /** Things the user should know about this result. */
  warnings: string[];
  /** Assumptions made while reading the file. */
  notes: string[];
}

function reportModel(spec: ModelSpec, result: EvaluationResult): ReportModel {
  const layer = spec.layers.find((l) => l.id === result.layer.id)!;
  return {
    id: spec.id,
    name: spec.name,
    version: spec.version,
    description: spec.description,
    max_reliable_years: spec.max_reliable_years,
    layer: { label: layer.label, description: layer.description, sources: layer.sources, kind: isScoreForm(layer.survival) ? "points" : "hazard" },
    inputs: Object.fromEntries(
      spec.inputs.map((i) => [i.id, { label: i.label, unit: i.type === "number" ? i.unit : null, source: i.source }]),
    ),
    sources: spec.sources,
    validation: spec.validation,
  };
}

export function runPrognosis(text: string, spec: ModelSpec, asOf: string): PrognosisReport {
  const record = parseUpload(text, asOf);
  const { observed, provenance } = extractInputs(spec, record, asOf);
  const result = evaluate(spec, observed);
  const warnings: string[] = [];
  if (!recordMatchesGroup(spec, record)) {
    warnings.push(`No ${spec.name.toLowerCase()} diagnosis was found in this record. Check that you picked the right disease group.`);
  }
  const latest = latestDate(record);
  if (!latest) warnings.push("The record has no dated entries, so we cannot tell how current it is.");
  else if (yearsBetween(latest, asOf) > STALE_AFTER_YEARS) {
    warnings.push(`The newest entry in this record is from ${latest}. The estimate may be out of date.`);
  }
  if (record.deceased) warnings.push("This record marks the patient as deceased.");
  return { format: record.format, asOf, model: reportModel(spec, result), result, provenance, warnings, notes: record.notes };
}
