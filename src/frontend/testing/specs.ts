/** Test-only: the full spec of every real model (folders starting with "_" excluded). */

import type { ModelSpec } from "../engine/spec";

export const REAL_SPECS: ModelSpec[] = Object.values(
  import.meta.glob<ModelSpec>(["../../prognosis-models/*/spec.json", "!../../prognosis-models/_*/spec.json"], { eager: true, import: "default" }),
);
