import type { PrognosisReport } from "../engine/prognosis";
import type { WorkerRequest, WorkerResponse } from "./protocol";

const TIMEOUT_MS = 120_000;

function todayIso(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Run one prognosis in a fresh worker, which is always terminated afterwards. */
export function runInWorker(file: File, modelId: string): Promise<PrognosisReport> {
  const worker = new Worker(new URL("./prognosis.worker.ts", import.meta.url), { type: "module" });
  return new Promise<PrognosisReport>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("The file took too long to analyse.")), TIMEOUT_MS);
    worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      clearTimeout(timer);
      if (event.data.ok) resolve(event.data.report);
      else reject(new Error(event.data.error));
    };
    // The worker itself failed to load or crashed (most likely out of memory on a huge file).
    worker.onerror = (event) => {
      clearTimeout(timer);
      console.error("Death's Warrant worker failed:", event.message || event);
      reject(new Error("The analysis stopped unexpectedly. The file may be too large for this device's memory."));
    };
    const request: WorkerRequest = { file, modelId, asOf: todayIso() };
    worker.postMessage(request);
  }).finally(() => worker.terminate());
}
