/**
 * Every model under src/models/<id>/spec.json, bundled at build time (no network fetch).
 * Adding a model folder is enough for it to appear; folders starting with "_" are excluded,
 * except that dev mode includes the unit-test fixture so the harness page can exercise it.
 */

import { SCHEMA_VERSION, type ModelSpec } from "./spec";

const real = import.meta.glob<ModelSpec>(["../../../models/*/spec.json", "!../../../models/_*/spec.json"], {
  eager: true,
  import: "default",
});
const fixture = import.meta.env.DEV
  ? import.meta.glob<ModelSpec>("../../../models/_fixture/spec.json", { eager: true, import: "default" })
  : {};

export const MODELS: ModelSpec[] = Object.values({ ...real, ...fixture })
  .filter((s) => s.schema_version === SCHEMA_VERSION)
  .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));

export function findModel(id: string): ModelSpec | undefined {
  return MODELS.find((m) => m.id === id);
}
