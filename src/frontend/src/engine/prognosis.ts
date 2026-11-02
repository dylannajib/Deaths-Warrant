/** The whole client-side pipeline: uploaded text → parsed record → inputs → prognosis. */

import { yearsBetween } from "../parsing/dates";
import type { SourceFormat } from "../parsing/record";
import { latestDate, parseUpload } from "../parsing/upload";
import { evaluate, type EvaluationResult } from "./evaluate";
import { extractInputs, recordMatchesGroup } from "./extract";
import type { ModelSpec } from "./spec";

export const STALE_AFTER_YEARS = 1;

export interface PrognosisReport {
  format: SourceFormat;
  asOf: string;
  result: EvaluationResult;
  provenance: Record<string, string>;
  /** Things the user should know about this result. */
  warnings: string[];
  /** Assumptions made while reading the file. */
  notes: string[];
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
  return { format: record.format, asOf, result, provenance, warnings, notes: record.notes };
}
