/**
 * Format tests. The documents below are minimal structural snippets that exercise the parsers.
 * They carry no clinical meaning and are never used to judge model accuracy, which uses real
 * published data only (see src/backend/deaths_warrant/validation.py).
 */

import { describe, expect, it } from "vitest";
import { latestDate, parseUpload, UploadError } from "./upload";

const asOf = "2026-11-02";

const fhirBundle = {
  resourceType: "Bundle",
  type: "collection",
  entry: [
    { fullUrl: "urn:uuid:p1", resource: { resourceType: "Patient", id: "p1", birthDate: "1950-03-04", gender: "female", address: [{ country: "AU" }] } },
    {
      resource: {
        resourceType: "Condition",
        code: { coding: [{ system: "http://hl7.org/fhir/sid/icd-10-cm", code: "I50.22", display: "Chronic systolic HF" }] },
        onsetDateTime: "2021-05-01",
      },
    },
    {
      resource: {
        resourceType: "Condition",
        verificationStatus: { coding: [{ code: "refuted" }] },
        code: { coding: [{ system: "http://snomed.info/sct", code: "13645005" }] },
      },
    },
    {
      resource: {
        resourceType: "Observation",
        status: "final",
        code: { coding: [{ system: "http://loinc.org", code: "10230-1" }] },
        valueQuantity: { value: 35, unit: "%", code: "%" },
        effectiveDateTime: "2025-01-10T09:00:00Z",
      },
    },
    {
      resource: {
        resourceType: "Observation",
        status: "final",
        code: { coding: [{ system: "http://loinc.org", code: "85354-9" }] },
        component: [
          { code: { coding: [{ system: "http://loinc.org", code: "8480-6" }] }, valueQuantity: { value: 118, code: "mm[Hg]" } },
          { code: { coding: [{ system: "http://loinc.org", code: "8462-4" }] }, valueQuantity: { value: 70, code: "mm[Hg]" } },
        ],
        effectiveDateTime: "2025-02-01",
      },
    },
    { fullUrl: "Medication/m1", resource: { resourceType: "Medication", id: "m1", code: { coding: [{ system: "http://www.nlm.nih.gov/research/umls/rxnorm", code: "866924", display: "metoprolol" }] } } },
    { resource: { resourceType: "MedicationRequest", status: "active", medicationReference: { reference: "Medication/m1" }, authoredOn: "2025-02-01" } },
  ],
};

describe("FHIR JSON", () => {
  const record = parseUpload(JSON.stringify(fhirBundle), asOf);

  it("reads the patient", () => {
    expect(record).toMatchObject({ format: "fhir-json", birthDate: "1950-03-04", sex: "female", country: "AU" });
  });

  it("normalises ICD codes and skips refuted conditions", () => {
    expect(record.conditions).toEqual([
      { codes: [{ system: "icd10", code: "I5022", display: "Chronic systolic HF" }], onset: "2021-05-01" },
    ]);
  });

  it("reads quantities and observation components", () => {
    expect(record.observations.map((o) => [o.codes[0]?.code, o.value, o.date])).toEqual([
      ["10230-1", 35, "2025-01-10"],
      ["8480-6", 118, "2025-02-01"],
      ["8462-4", 70, "2025-02-01"],
    ]);
  });

  it("resolves medication references", () => {
    expect(record.medications[0]?.codes[0]).toMatchObject({ system: "rxnorm", code: "866924" });
    expect(latestDate(record)).toBe("2025-02-01");
  });

  it("dates an undated encounter diagnosis from its visit", () => {
    const visit = {
      resourceType: "Bundle",
      entry: [
        { resource: { resourceType: "Patient", id: "p1", birthDate: "1950-03-04" } },
        { fullUrl: "Encounter/e1", resource: { resourceType: "Encounter", id: "e1", period: { start: "2024-07-02T10:00:00Z" } } },
        { resource: { resourceType: "Condition", code: { coding: [{ system: "http://hl7.org/fhir/sid/icd-9-cm", code: "428.0" }] }, encounter: { reference: "Encounter/e1" } } },
      ],
    };
    const r = parseUpload(JSON.stringify(visit), asOf);
    expect(r.conditions[0]?.onset).toBe("2024-07-02");
    expect(r.notes.join(" ")).toMatch(/start of the hospital visit/);
  });

  it("marks diagnoses recorded during a hospital stay with the admission date", () => {
    const hf = { coding: [{ system: "http://hl7.org/fhir/sid/icd-10-cm", code: "I50.9" }] };
    const stays = {
      resourceType: "Bundle",
      entry: [
        { resource: { resourceType: "Patient", id: "p1", birthDate: "1950-03-04" } },
        { resource: { resourceType: "Encounter", id: "inp", class: { system: "http://terminology.hl7.org/CodeSystem/v3-ActCode", code: "IMP" }, period: { start: "2026-08-01" } } },
        // MIMIC style: emergency class, but an admission lasting past its first day
        { resource: { resourceType: "Encounter", id: "emer", class: { code: "EMER" }, hospitalization: {}, period: { start: "2026-05-01T10:00", end: "2026-05-04T12:00" } } },
        { resource: { resourceType: "Encounter", id: "ed", class: { code: "EMER" }, period: { start: "2026-09-01T10:00", end: "2026-09-01T16:00" } } },
        // R5 diagnosis list on the encounter pointing at the condition
        { resource: { resourceType: "Encounter", id: "r5", class: [{ coding: [{ code: "ACUTE" }] }], period: { start: "2026-10-01" }, diagnosis: [{ condition: [{ reference: { reference: "Condition/c4" } }] }] } },
        { resource: { resourceType: "Condition", id: "c1", code: hf, encounter: { reference: "Encounter/inp" } } },
        { resource: { resourceType: "Condition", id: "c2", code: hf, encounter: { reference: "Encounter/emer" } } },
        { resource: { resourceType: "Condition", id: "c3", code: hf, encounter: { reference: "Encounter/ed" } } },
        { resource: { resourceType: "Condition", id: "c4", code: hf, onsetDateTime: "2019-01-01" } },
        // R4 diagnosis list pointing at a urn:uuid fullUrl, on a Condition without an id
        { resource: { resourceType: "Encounter", id: "r4", class: { code: "IMP" }, period: { start: "2026-09-15" }, diagnosis: [{ condition: { reference: "urn:uuid:c5" } }] } },
        { fullUrl: "urn:uuid:c5", resource: { resourceType: "Condition", code: hf } },
        { resource: { resourceType: "Condition", code: hf } }, // no id, no encounter: not a stay
      ],
    };
    const r = parseUpload(JSON.stringify(stays), asOf);
    expect(r.conditions.map((c) => c.admitted)).toEqual(["2026-08-01", "2026-05-01", undefined, "2026-10-01", "2026-09-15", undefined]);
    expect(r.conditions[3]?.onset).toBe("2019-01-01");
  });

  it("rejects multiple patients", () => {
    const two = { ...fhirBundle, entry: [...fhirBundle.entry, { resource: { resourceType: "Patient", id: "p2" } }] };
    expect(() => parseUpload(JSON.stringify(two), asOf)).toThrow(/more than one patient/);
  });
});

describe("FHIR XML", () => {
  const xml = `<Bundle xmlns="http://hl7.org/fhir">
    <type value="collection"/>
    <entry><resource><Patient>
      <id value="p1"/>
      <text><div xmlns="http://www.w3.org/1999/xhtml"><script>alert(1)</script></div></text>
      <gender value="male"/><birthDate value="1948-11-20"/>
    </Patient></resource></entry>
    <entry><resource><Condition>
      <code><coding><system value="http://snomed.info/sct"/><code value="13645005"/><display value="COPD"/></coding></code>
      <onsetDateTime value="2019-06"/>
    </Condition></resource></entry>
  </Bundle>`;

  it("reads the same structure as JSON and ignores narrative HTML", () => {
    const record = parseUpload(xml, asOf);
    expect(record).toMatchObject({ format: "fhir-xml", sex: "male", birthDate: "1948-11-20" });
    expect(record.conditions).toEqual([{ codes: [{ system: "snomed", code: "13645005", display: "COPD" }], onset: "2019-06-15" }]);
  });
});

describe("C-CDA", () => {
  const ccda = `<?xml version="1.0"?>
  <ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <recordTarget><patientRole>
      <addr><country>US</country></addr>
      <patient><administrativeGenderCode code="M"/><birthTime value="19520115"/></patient>
    </patientRole></recordTarget>
    <component><structuredBody>
      <component><section>
        <entry><act><entryRelationship><observation classCode="OBS" moodCode="EVN">
          <templateId root="2.16.840.1.113883.10.20.22.4.4"/>
          <effectiveTime><low value="20200310"/></effectiveTime>
          <value xsi:type="CD" code="C34.90" codeSystem="2.16.840.1.113883.6.90" displayName="Lung cancer">
            <translation code="254637007" codeSystem="2.16.840.1.113883.6.96"/>
          </value>
        </observation></entryRelationship></act></entry>
        <entry><observation negationInd="true">
          <templateId root="2.16.840.1.113883.10.20.22.4.4"/>
          <value xsi:type="CD" code="I50.9" codeSystem="2.16.840.1.113883.6.90"/>
        </observation></entry>
      </section></component>
      <component><section>
        <entry><organizer><component><observation>
          <code code="2160-0" codeSystem="2.16.840.1.113883.6.1"/>
          <effectiveTime value="20250105"/>
          <value xsi:type="PQ" value="1.4" unit="mg/dL"/>
        </observation></component></organizer></entry>
      </section></component>
      <component><section>
        <entry><substanceAdministration>
          <effectiveTime><low value="20240101"/></effectiveTime>
          <consumable><manufacturedProduct><manufacturedMaterial>
            <code code="197361" codeSystem="2.16.840.1.113883.6.88"><originalText>Amlodipine 5 mg</originalText></code>
          </manufacturedMaterial></manufacturedProduct></consumable>
        </substanceAdministration></entry>
      </section></component>
    </structuredBody></component>
  </ClinicalDocument>`;

  const record = parseUpload(ccda, asOf);

  it("reads patient, problems (with translations), results and medications", () => {
    expect(record).toMatchObject({ format: "ccda", sex: "male", birthDate: "1952-01-15", country: "US" });
    expect(record.conditions).toEqual([
      {
        codes: [
          { system: "icd10", code: "C3490", display: "Lung cancer" },
          { system: "snomed", code: "254637007" },
        ],
        onset: "2020-03-10",
      },
    ]);
    expect(record.observations).toEqual([{ codes: [{ system: "loinc", code: "2160-0" }], value: 1.4, unit: "mg/dL", date: "2025-01-05" }]);
    expect(record.medications).toEqual([{ codes: [{ system: "rxnorm", code: "197361" }], text: "Amlodipine 5 mg", date: "2024-01-01" }]);
  });

  const problem = (code: string) => `<entryRelationship><observation><templateId root="2.16.840.1.113883.10.20.22.4.4"/>
    <value xsi:type="CD" code="${code}" codeSystem="2.16.840.1.113883.6.90"/></observation></entryRelationship>`;
  const encounter = (code: string, system: string, date: string, dx: string) => `<entry><encounter>
    <templateId root="2.16.840.1.113883.10.20.22.4.49"/><code code="${code}" codeSystem="${system}"/>
    <effectiveTime><low value="${date}"/></effectiveTime>${problem(dx)}</encounter></entry>`;

  it("marks problems recorded in an inpatient encounter or a discharge diagnosis", () => {
    const doc = `<ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <recordTarget><patientRole><patient><birthTime value="19520115"/></patient></patientRole></recordTarget>
      <componentOf><encompassingEncounter><effectiveTime><low value="20260901"/><high value="20260905"/></effectiveTime></encompassingEncounter></componentOf>
      <component><structuredBody><component><section>
        ${encounter("99222", "2.16.840.1.113883.6.12", "20260601", "I50.9")}
        ${encounter("99213", "2.16.840.1.113883.6.12", "20260701", "I50.1")}
        ${encounter("IMP", "2.16.840.1.113883.5.4", "20260801", "I50.2")}
        <entry><act><templateId root="2.16.840.1.113883.10.20.22.4.33"/>${problem("I50.3")}</act></entry>
      </section></component></structuredBody></component>
    </ClinicalDocument>`;
    const r = parseUpload(doc, asOf);
    expect(r.conditions.map((c) => [c.codes[0]?.code, c.admitted])).toEqual([
      ["I509", "2026-06-01"],
      ["I501", undefined], // office visit
      ["I502", "2026-08-01"],
      ["I503", "2026-09-01"], // discharge diagnosis: the document's hospital stay
    ]);
  });
});

describe("upload validation", () => {
  it.each([
    ["binary content", "\u0000\u0001PK"],
    ["plain text", "hello"],
    ["invalid JSON", "{ nope"],
    ["a non-patient FHIR resource", JSON.stringify({ resourceType: "Observation" })],
    ["unrelated XML", "<html><body/></html>"],
    ["XML with a DOCTYPE", `<!DOCTYPE x><Bundle xmlns="http://hl7.org/fhir"/>`],
    ["hostile JSON nesting", "{\"resourceType\":\"Patient\",\"x\":" + "[".repeat(300) + "]".repeat(300) + "}"],
  ])("rejects %s", (_, text) => {
    expect(() => parseUpload(text, asOf)).toThrow(UploadError);
  });

  it("notes how ambiguous dates were read", () => {
    const doc = { resourceType: "Patient", birthDate: "03/04/1950", address: [{ country: "US" }] };
    const record = parseUpload(JSON.stringify(doc), asOf);
    expect(record.birthDate).toBe("1950-03-04");
    expect(record.notes[0]).toMatch(/month\/day\/year.*US/);
  });

  it("accepts a byte-order mark", () => {
    expect(parseUpload("﻿" + JSON.stringify({ resourceType: "Patient", birthDate: "1950-01-01" }), asOf).birthDate).toBe("1950-01-01");
  });
});
