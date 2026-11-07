/// <reference lib="webworker" />
/**
 * Runs the pipeline off the main thread so large files never freeze the page.
 * The client terminates this worker after one run, releasing the file from memory.
 */

import { MissingInputError } from "../engine/evaluate";
import { loadModel } from "../engine/loader";
import { describeFailure } from "../errors";
import { runPrognosis } from "../engine/prognosis";
import type { WorkerRequest, WorkerResponse } from "./protocol";

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  let response: WorkerResponse;
  try {
    const { file, modelId, asOf, entered } = event.data;
    const spec = await loadModel(modelId);
    if (!spec) throw new Error("Unknown disease group");
    response = { ok: true, report: runPrognosis(await file.text(), spec, asOf, entered) };
  } catch (e) {
    response = { ok: false, error: describeFailure(e), missing: e instanceof MissingInputError ? e.input : null };
  }
  self.postMessage(response);
};
