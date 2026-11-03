/** Worker-only: the full spec of a listed model, each in its own chunk loaded on demand. */

import { MODELS, SUMMARY_PATHS } from "./models";
import type { ModelSpec } from "./spec";

const specs = {
  ...import.meta.glob<ModelSpec>(["../../../models/*/spec.json", "!../../../models/_*/spec.json"], { import: "default" }),
  ...(import.meta.env.DEV ? import.meta.glob<ModelSpec>("../../../models/_fixture/spec.json", { import: "default" }) : {}),
};

/** The full spec for a listed model, or undefined for an unknown id. */
export async function loadModel(id: string): Promise<ModelSpec | undefined> {
  const summary = MODELS.find((m) => m.id === id);
  const path = summary && SUMMARY_PATHS.get(summary)?.replace("summary.json", "spec.json");
  return path ? specs[path]?.() : undefined;
}
