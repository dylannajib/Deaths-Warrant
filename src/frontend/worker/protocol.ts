import type { PrognosisReport } from "../engine/prognosis";

export interface WorkerRequest {
  file: File;
  modelId: string;
  asOf: string;
}

export type WorkerResponse = { ok: true; report: PrognosisReport } | { ok: false; error: string };
