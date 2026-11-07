import type { Observed } from "../engine/evaluate";
import type { PrognosisReport } from "../engine/prognosis";
import type { Input } from "../engine/spec";

export interface WorkerRequest {
  file: File;
  modelId: string;
  asOf: string;
  /** Values the user typed in for required inputs the record lacks. */
  entered: Observed;
}

/** `missing` is set when a required input is missing, so the page can ask the user for it. */
export type WorkerResponse = { ok: true; report: PrognosisReport } | { ok: false; error: string; missing: Input | null };
