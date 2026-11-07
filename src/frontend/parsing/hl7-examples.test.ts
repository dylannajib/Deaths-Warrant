/**
 * Parsers on official HL7 example documents (CC0, see fixtures/README.md): real-world C-CDA
 * and FHIR structure, including the XML and JSON forms of the same FHIR resources.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseUpload } from "./upload";

const read = (name: string) => readFileSync(join(__dirname, "fixtures", name), "utf-8");
const parse = (name: string) => parseUpload(read(name), "2026-11-03");
const codes = (r: ReturnType<typeof parse>) => r.conditions.flatMap((c) => c.codes.map((x) => `${x.system}:${x.code}`));

describe("HL7 C-CDA examples", () => {
  it("reads the CCD's patient, problems and medications, but not its vaccines", () => {
    const r = parse("ccda-ccd-1.xml");
    expect(r).toMatchObject({ format: "ccda", birthDate: "1975-05-01", sex: "female" });
    expect(codes(r)).toEqual(expect.arrayContaining(["snomed:233604007", "snomed:194828000"]));
    expect(r.medications.map((m) => m.codes[0]?.code)).toEqual(["573621", "197380"]);
    expect(r.observations.length).toBeGreaterThan(10);
  });

  it("ignores the example's malformed dates instead of guessing", () => {
    expect(parse("ccda-ccd-1.xml").notes).toContain("1 unreadable date(s) ignored.");
  });

  it("reads vital signs and an empty problem list", () => {
    const r = parse("ccda-ccd-2.xml");
    expect(r).toMatchObject({ birthDate: "1950-12-19", sex: "female", conditions: [] });
    const bp = r.observations.find((o) => o.codes.some((c) => c.code === "8480-6"));
    expect(bp).toMatchObject({ value: 120, unit: "mm[Hg]", date: "2014-10-01" });
  });

  it("reads a discharge summary's diagnoses", () => {
    const r = parse("ccda-discharge-summary.xml");
    expect(r).toMatchObject({ birthDate: "2005-05-01", sex: "female" });
    expect(codes(r)).toContain("snomed:74400008");
  });
});

describe("FHIR R4 examples", () => {
  it.each(["fhir-r4-patient-example", "fhir-r4-document-example-dischargesummary"])(
    "%s: the XML and JSON forms give the same record",
    (name) => {
      const xml = parse(`${name}.xml`);
      const json = parse(`${name}.json`);
      expect(xml.format).toBe("fhir-xml");
      expect({ ...xml, format: "fhir-json" }).toEqual(json);
    },
  );

  it("reads the discharge summary's patient and medications", () => {
    const r = parse("fhir-r4-document-example-dischargesummary.json");
    expect(r).toMatchObject({ birthDate: "1955-01-06", sex: "female" });
    expect(r.medications.map((m) => m.text)).toEqual(["Theophylline 200mg", "Ventolin Inhaler"]);
  });
});
