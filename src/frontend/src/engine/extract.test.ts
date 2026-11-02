import { describe, expect, it } from "vitest";
import type { PatientRecord } from "../parsing/record";
import { extractInputs, recordMatchesGroup } from "./extract";
import type { Input, ModelSpec } from "./spec";

const input = (id: string, extract: Input["extract"], type: Input["type"] = "number"): Input =>
  ({ id, label: id, extract, missing: [], source: null, type, min: 0, max: 1e6, unit: null, values: ["a", "b"] }) as Input;

const none = { icd10: [], icd9: [], snomed: [] };
const spec = {
  group_codes: { ...none, icd10: ["I50"] },
  inputs: [
    input("age", { rule: "age" }),
    input("sex", { rule: "sex" }, "enum"),
    input("creat", { rule: "observation_number", loinc: ["2160-0"], units: { "mg/dl": 88.4, "umol/l": 1 }, max_age_days: null }),
    input("stage", { rule: "observation_coded", loinc: ["21908-9"], values: { "snomed:1": "a", "text:stage iv": "b" }, max_age_days: null }, "enum"),
    input("dx", { rule: "condition_category", categories: [{ value: "a", codes: { ...none, icd10: ["I50"] } }, { value: "b", codes: { ...none, snomed: ["13645005"] } }] }, "enum"),
    input("copd", { rule: "condition_present", codes: { ...none, snomed: ["13645005"] } }, "boolean"),
    input("cci", { rule: "condition_weighted_sum", groups: [{ weight: 1, codes: { ...none, icd10: ["I50"] } }, { weight: 2, codes: { ...none, icd10: ["E11"] } }] }),
    input("years", { rule: "years_since_condition", codes: { ...none, icd10: ["I50"] } }),
    input("cat_years", { rule: "years_since_category", categories: [{ value: "x", codes: { ...none, icd10: ["Z99"] } }, { value: "a", codes: { ...none, icd10: ["I50"] } }] }),
    input("bb", { rule: "medication_present", rxnorm: [], atc: ["C07"], names: ["bisoprolol"] }, "boolean"),
    input("first", { rule: "first_of", rules: [
      { rule: "condition_category", categories: [{ value: "a", codes: { ...none, icd10: ["C79"] } }] },
      { rule: "observation_coded", loinc: ["21908-9"], values: { "text:stage iv": "b" }, max_age_days: null },
    ] }, "enum"),
  ],
} as unknown as ModelSpec;

const record: PatientRecord = {
  format: "fhir-json",
  birthDate: "1950-11-02",
  sex: "male",
  conditions: [
    { codes: [{ system: "icd10", code: "I5022" }], onset: "2020-11-02" },
    { codes: [{ system: "snomed", code: "13645005" }] },
  ],
  observations: [
    { codes: [{ system: "loinc", code: "2160-0" }], value: 1.0, unit: "mg/dL", date: "2024-01-01" },
    { codes: [{ system: "loinc", code: "2160-0" }], value: 100, unit: "umol/L", date: "2025-01-01" },
    { codes: [{ system: "loinc", code: "2160-0" }], value: 9, unit: "furlongs", date: "2026-01-01" },
    { codes: [{ system: "loinc", code: "21908-9" }], valueText: "Stage IV", date: "2025-01-01" },
  ],
  medications: [{ codes: [], text: "Bisoprolol 2.5mg" }],
  notes: [],
};

describe("extractInputs", () => {
  const { observed, provenance } = extractInputs(spec, record, "2026-11-02");

  it("applies every rule type", () => {
    expect(observed.age).toBeCloseTo(76, 1);
    expect(observed).toMatchObject({ sex: "male", creat: 100, stage: "b", dx: "a", copd: true, cci: 1, bb: true, first: "b" });
    expect(observed.years).toBeCloseTo(6, 1);
    expect(observed.cat_years).toBeCloseTo(6, 1);
  });

  it("first_of falls through to the first rule that yields a value", () => {
    expect(provenance.first).toMatch(/Stage IV/);
  });

  it("treats medication as unknown when the record lists no medications", () => {
    expect(extractInputs(spec, { ...record, medications: [] }, "2026-11-02").observed.bb).toBeNull();
  });

  it("ignores measurements in unknown units", () => {
    expect(provenance.creat).toMatch(/100 umol\/L on 2025-01-01/);
  });

  it("matches the disease group by code prefix", () => {
    expect(recordMatchesGroup(spec, record)).toBe(true);
    expect(recordMatchesGroup(spec, { ...record, conditions: [] })).toBe(false);
  });
});
