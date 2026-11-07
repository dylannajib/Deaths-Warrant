import type { Observed } from "../engine/evaluate";
import type { PrognosisReport } from "../engine/prognosis";
import type { Input } from "../engine/spec";
import type { WorkerRequest, WorkerResponse } from "./protocol";

const TIMEOUT_MS = 120_000;

function todayIso(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** A failed run. `missing` is the required input to ask the user for, if that is what failed. */
export class RunError extends Error {
  constructor(message: string, readonly missing: Input | null = null) {
    super(message);
  }
}

/** Run one prognosis in a fresh worker, which is always terminated afterwards. */
export function runInWorker(file: File, modelId: string, entered: Observed = {}): Promise<PrognosisReport> {
  const worker = new Worker(new URL("./prognosis.worker.ts", import.meta.url), { type: "module" });
  return new Promise<PrognosisReport>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("The file took too long to analyse.")), TIMEOUT_MS);
    worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      clearTimeout(timer);
      if (event.data.ok) resolve(event.data.report);
      else reject(new RunError(event.data.error, event.data.missing));
    };
    // The worker itself failed to load or crashed (most likely out of memory on a huge file).
    worker.onerror = (event) => {
      clearTimeout(timer);
      console.error("Death's Warrant worker failed:", event.message || event);
      reject(new Error("The analysis stopped unexpectedly. The file may be too large for this device's memory."));
    };
    const request: WorkerRequest = { file, modelId, asOf: todayIso(), entered };
    worker.postMessage(request);
  }).finally(() => worker.terminate());
}
