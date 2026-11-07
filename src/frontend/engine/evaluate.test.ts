import { describe, expect, it } from "vitest";
import { evaluate, EvaluationError, MissingInputError, populationCumHazard, solveTime, type Observed } from "./evaluate";
import type { ModelSpec } from "./spec";

interface Golden {
  observed: Observed;
  expected: Pick<ReturnType<typeof evaluate>, "layer" | "median_years" | "range_low_years" | "range_high_years" | "survival_at">;
}

// Every exported model (and the unit-test fixture) must reproduce the Python reference.
const specs = import.meta.glob<ModelSpec>("../../prognosis-models/*/spec.json", { eager: true, import: "default" });
const goldens = import.meta.glob<Golden[]>("../../prognosis-models/*/golden.json", { eager: true, import: "default" });

const close = (a: number | null, b: number | null) => {
  if (a === null || b === null) return expect(a).toBe(b);
  expect(Math.abs(a - b)).toBeLessThanOrEqual(1e-9 * Math.max(1, Math.abs(b)));
};

describe("golden parity with the Python reference evaluator", () => {
  const entries = Object.entries(goldens);
  it("finds golden files", () => expect(entries.length).toBeGreaterThan(0));
  for (const [path, cases] of entries) {
    const spec = specs[path.replace("golden.json", "spec.json")]!;
    cases.forEach((c, k) => {
      it(`${spec.id} case ${k}`, () => {
        const r = evaluate(spec, c.observed);
        expect(r.layer).toEqual(c.expected.layer);
        close(r.median_years, c.expected.median_years);
        close(r.range_low_years, c.expected.range_low_years);
        close(r.range_high_years, c.expected.range_high_years);
        for (const t of Object.keys(c.expected.survival_at)) close(r.survival_at[t]!, c.expected.survival_at[t]!);
      });
    });
  }
});

describe("evaluator details", () => {
  const fixture = specs["../../prognosis-models/_fixture/spec.json"]!;

  it("requires mandatory inputs", () => {
    expect(() => evaluate(fixture, { score: 4 })).toThrow(EvaluationError);
  });

  it("names the missing input, so the page can ask the user for it", () => {
    let error: unknown;
    try {
      evaluate(fixture, { score: 4, age: 500 }); // implausible counts as missing
    } catch (e) {
      error = e;
    }
    expect(error).toBeInstanceOf(MissingInputError);
    expect((error as MissingInputError).input.id).toBe("age");
    expect((error as MissingInputError).message).toBe("Age is required but was not found in the record");
  });

  it("reports which inputs were assumed", () => {
    const r = evaluate(fixture, { age: 60, score: 4 });
    expect(r.inputs.find((i) => i.id === "flag")?.assumed).toHaveLength(2);
    expect(r.inputs.find((i) => i.id === "sex")?.status).toBe("unused");
  });

  it("integrates the life table across ages", () => {
    const h = populationCumHazard([0.1, 0.2, 0.3], 0.5, 2);
    expect(h).toBeCloseTo(-(0.5 * Math.log(0.9) + Math.log(0.8) + 0.5 * Math.log(0.7)), 12);
  });

  it("returns null beyond the horizon", () => {
    expect(solveTime(() => 0.99, 0.5)).toBeNull();
  });
});
