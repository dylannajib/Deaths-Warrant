/// <reference lib="webworker" />
/**
 * Runs the pipeline off the main thread so large files never freeze the page.
 * The client terminates this worker after one run, releasing the file from memory.
 */

import { findModel } from "../engine/models";
import { runPrognosis } from "../engine/prognosis";
import type { WorkerRequest, WorkerResponse } from "./protocol";

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  let response: WorkerResponse;
  try {
    const { file, modelId, asOf } = event.data;
    const spec = findModel(modelId);
    if (!spec) throw new Error("Unknown disease group");
    response = { ok: true, report: runPrognosis(await file.text(), spec, asOf) };
  } catch (e) {
    response = { ok: false, error: e instanceof Error ? e.message : "Something went wrong reading the file." };
  }
  self.postMessage(response);
};
