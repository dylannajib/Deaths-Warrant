/** Worker-only: the full spec of a listed model, each in its own chunk loaded on demand. */

import { MODELS } from "./models";
import type { ModelSpec } from "./spec";

const specs = import.meta.glob<ModelSpec>(["../../prognosis-models/*/spec.json", "!../../prognosis-models/_*/spec.json"], { import: "default" });
// The exporter guarantees each spec's id is its folder name.
const byId = new Map(Object.entries(specs).map(([path, load]) => [path.split("/").at(-2)!, load]));

/** The full spec for a listed model, or undefined for an unknown id. */
export async function loadModel(id: string): Promise<ModelSpec | undefined> {
  return MODELS.some((m) => m.id === id) ? byId.get(id)?.() : undefined;
}
