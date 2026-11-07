import { describe, expect, it } from "vitest";
import { REAL_SPECS } from "../testing/specs";
import { MissingInputError } from "./evaluate";
import { GroupMismatchError, runPrognosis } from "./prognosis";

const cancer = REAL_SPECS.find((s) => s.id === "cancer")!;
const asOf = "2026-11-07";

// A patient with no birth date, and a lung cancer diagnosis only when asked for.
const record = (withCancer: boolean) =>
  JSON.stringify({
    resourceType: "Bundle",
    type: "collection",
    entry: [
      { resource: { resourceType: "Patient", id: "p", gender: "female" } },
      ...(withCancer
        ? [{ resource: { resourceType: "Condition", subject: { reference: "Patient/p" }, onsetDateTime: "2025-01-10",
            code: { coding: [{ system: "http://hl7.org/fhir/sid/icd-10-cm", code: "C34.90" }] } } }]
        : []),
    ],
  });

describe("runPrognosis checks, in order", () => {
  it("refuses the wrong disease group before asking for missing inputs", () => {
    expect(() => runPrognosis(record(false), cancer, asOf)).toThrow(GroupMismatchError);
  });

  it("then asks for a missing required input", () => {
    expect(() => runPrognosis(record(true), cancer, asOf)).toThrow(MissingInputError);
  });

  it("then runs with the value the user typed in", () => {
    const report = runPrognosis(record(true), cancer, asOf, { age: 70 });
    expect(report.result.inputs.find((i) => i.id === "age")?.value).toBe(70);
    expect(report.provenance.age).toBe("Your manual input");
  });
});
