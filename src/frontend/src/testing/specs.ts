/** Test-only: the full spec of every real model (folders starting with "_" excluded). */

import type { ModelSpec } from "../engine/spec";

export const REAL_SPECS: ModelSpec[] = Object.values(
  import.meta.glob<ModelSpec>(["../../../models/*/spec.json", "!../../../models/_*/spec.json"], { eager: true, import: "default" }),
);
