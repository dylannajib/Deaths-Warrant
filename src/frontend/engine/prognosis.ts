/** The whole client-side pipeline: uploaded text → parsed record → inputs → prognosis. */

import { RecordError } from "../errors";
import { formatDate, yearsBetween } from "../parsing/dates";
import type { SourceFormat } from "../parsing/record";
import { latestDate, parseUpload } from "../parsing/upload";
import { evaluate, type EvaluationResult, type Observed } from "./evaluate";
import { extractInputs, recordMatchesGroup } from "./extract";
import { isScoreForm, lifeTableOf, type ModelSpec, type Source, type ValidationResult } from "./spec";

const STALE_AFTER_YEARS = 1;

/** The parts of the spec the Reasoning panel shows (the page never loads the full spec). */
interface ReportModel {
  name: string;
  version: string;
  max_reliable_years: number;
  /** The population life table the layer uses, e.g. "United States life tables, 2024", or null. */
  population: string | null;
  layer: { label: string; description: string; sources: string[]; kind: "points" | "hazard" };
  inputs: Record<string, { label: string; unit: string | null }>;
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

export function reportModel(spec: ModelSpec, result: EvaluationResult): ReportModel {
  const layer = spec.layers.find((l) => l.id === result.layer.id)!;
  const table = lifeTableOf(layer.survival);
  return {
    name: spec.name,
    version: spec.version,
    max_reliable_years: spec.max_reliable_years,
    population: table === null ? null : spec.life_tables[table]!.label,
    layer: { label: layer.label, description: layer.description, sources: layer.sources, kind: isScoreForm(layer.survival) ? "points" : "hazard" },
    inputs: Object.fromEntries(
      spec.inputs.map((i) => [i.id, { label: i.label, unit: i.type === "number" ? i.unit : null }]),
    ),
    sources: spec.sources,
    validation: spec.validation,
  };
}

/** The record has no diagnosis from the chosen disease group, so no estimate is made. */
export class GroupMismatchError extends RecordError {}

/** `entered` holds values the user typed in for required inputs the record lacks. They win over the record. */
export function runPrognosis(text: string, spec: ModelSpec, asOf: string, entered: Observed = {}): PrognosisReport {
  const record = parseUpload(text, asOf);
  if (!recordMatchesGroup(spec, record)) {
    throw new GroupMismatchError(`No ${spec.name.toLowerCase()} diagnosis found on this record.\nCheck that you selected the right disease group.`);
  }
  const { observed, provenance } = extractInputs(spec, record, asOf);
  for (const [id, value] of Object.entries(entered)) {
    observed[id] = value;
    provenance[id] = "Your manual input";
  }
  const result = evaluate(spec, observed);
  const warnings: string[] = [];
  const latest = latestDate(record);
  if (!latest) warnings.push("The record has no dated entries, so we cannot tell how current it is.");
  else if (yearsBetween(latest, asOf) > STALE_AFTER_YEARS) {
    warnings.push(`The newest entry in this record is from ${formatDate(latest)}. The estimate may be out of date.`);
  }
  if (record.deceased) warnings.push("The record marks the patient as deceased.");
  return { format: record.format, asOf, model: reportModel(spec, result), result, provenance, warnings, notes: record.notes };
}
