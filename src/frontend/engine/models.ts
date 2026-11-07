/**
 * Every model under src/prognosis-models/<id>/, bundled at build time (no network fetch to another
 * site). Adding a model folder is enough for it to appear. Folders starting with "_" are skipped.
 *
 * The page imports only each model's summary.json (name and description, a few hundred
 * bytes). The full spec.json, with its coefficient tables and code lists, is loaded by the
 * worker alone, through loader.ts, for the model the user picked.
 */

import { SCHEMA_VERSION, type ModelSpec } from "./spec";

type ModelSummary = Pick<ModelSpec, "schema_version" | "id" | "name" | "order" | "description">;

const summaries = import.meta.glob<ModelSummary>(["../../prognosis-models/*/summary.json", "!../../prognosis-models/_*/summary.json"], {
  eager: true,
  import: "default",
});

export const MODELS: ModelSummary[] = Object.values(summaries)
  .filter((s) => s.schema_version === SCHEMA_VERSION)
  .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
