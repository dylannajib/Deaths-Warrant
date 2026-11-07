/**
 * Hostile and malformed uploads. The contract: whatever the file, the pipeline either returns
 * a report or throws one of our own errors with a readable message (UploadError while reading,
 * EvaluationError when a required input such as the birth date is missing, GroupMismatchError
 * when the record has no diagnosis from the chosen disease group). Never a crash,
 * never a hang, never a change to JavaScript's built-in objects.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { EvaluationError } from "../engine/evaluate";
import { GroupMismatchError, runPrognosis } from "../engine/prognosis";
import { parseUpload, UploadError } from "./upload";
import { REAL_SPECS } from "../testing/specs";

const asOf = "2026-11-03";
const specs = REAL_SPECS;
const fixtures = ["ccda-ccd-1.xml", "ccda-ccd-2.xml", "ccda-discharge-summary.xml", "fhir-r4-patient-example.xml",
  "fhir-r4-patient-example.json", "fhir-r4-document-example-dischargesummary.xml", "fhir-r4-document-example-dischargesummary.json"]
  .map((name) => readFileSync(join(__dirname, "fixtures", name), "utf-8")); // prettier-ignore

const rejects = (text: string, message: RegExp) => expect(() => parseUpload(text, asOf)).toThrow(message);
const patient = (inner: string) => `<Bundle xmlns="http://hl7.org/fhir"><entry><resource><Patient><birthDate value="1950-01-01"/>${inner}</Patient></resource></entry></Bundle>`;

describe("known attacks", () => {
  it("rejects external entities (XXE)", () =>
    rejects(`<?xml version="1.0"?><!DOCTYPE p [<!ENTITY x SYSTEM "file:///etc/passwd">]><Patient xmlns="http://hl7.org/fhir">&x;</Patient>`, /not allowed/));

  it("rejects entity expansion (billion laughs)", () =>
    rejects(`<!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]><Patient xmlns="http://hl7.org/fhir">&b;</Patient>`, /not allowed/));

  it("rejects entities that only exist on Object.prototype", () => {
    rejects(patient("<name>&valueOf;</name>"), /Unsupported entity/);
    rejects(patient("<name>&toString;</name>"), /Unsupported entity/);
  });

  it("treats prototype-named XML elements and attributes as plain data", () => {
    const record = parseUpload(patient(`<__proto__ value="x"/><constructor value="y"/><gender constructor="z" value="male"/>`), asOf);
    expect(record.sex).toBe("male");
    expect(({} as Record<string, unknown>).value).toBeUndefined();
  });

  it("does not pollute Object.prototype from JSON", () => {
    const json = `{"resourceType":"Bundle","__proto__":{"polluted":1},"entry":[{"resource":{"resourceType":"Patient","constructor":{"prototype":{"polluted":1}},"birthDate":"1950-01-01"}}]}`;
    parseUpload(json, asOf);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });

  it("rejects extreme nesting without overflowing the stack", () => {
    rejects(`{"resourceType":"Bundle","entry":${"[".repeat(100_000)}${"]".repeat(100_000)}}`, /nested too deeply/);
    rejects(`<Bundle xmlns="http://hl7.org/fhir">${"<a>".repeat(100_000)}${"</a>".repeat(100_000)}</Bundle>`, /nested too deeply/);
  });

  it("rejects binary, empty and non-record files", () => {
    rejects("\u0000\u0001ELF", /UploadError|binary|not a/i);
    rejects("", /Unrecognised file/);
    rejects("[1, 2, 3]", /FHIR/);
    rejects(`{"resourceType":"Observation"}`, /Bundle or Patient/);
    rejects(`<html><body><script>alert(1)</script></body></html>`, /FHIR|C-CDA|ClinicalDocument/);
    rejects(`<Patient xmlns="http://evil.example/fhir"><birthDate value="1950-01-01"/></Patient>`, /FHIR|C-CDA|namespace/i);
  });
});

describe("fuzzing real document structure", () => {
  // Deterministic PRNG (mulberry32) so any failure is reproducible.
  let seed = 20261103;
  const rand = () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const pick = <T>(xs: T[]) => xs[Math.floor(rand() * xs.length)]!;
  const tokens = ["<", ">", "&", "&amp;", "&#0;", "&#xFFFFFFF;", '"', "'", "<!DOCTYPE x>", "<![CDATA[", "]]>", "</", "/>",
    "{", "}", "[", "]", ",", ":", "\\", "\u0000", "__proto__", "constructor", "9999-99-99", "-1e309", "NaN", "\uD800"]; // prettier-ignore
  const mutate = (text: string) => {
    let out = text;
    for (let k = 0, n = 1 + Math.floor(rand() * 4); k < n; k++) {
      const at = Math.floor(rand() * out.length);
      switch (Math.floor(rand() * 4)) {
        case 0: out = out.slice(0, at) + pick(tokens) + out.slice(at); break; // insert
        case 1: out = out.slice(0, at) + out.slice(at + 1 + Math.floor(rand() * 40)); break; // delete
        case 2: out = out.slice(0, at); break; // truncate
        default: { const from = Math.floor(rand() * out.length); out = out.slice(0, at) + out.slice(from, from + 200) + out.slice(at); } // duplicate
      }
    }
    return out;
  };

  it("only ever returns a report or throws our own errors (2,800 mutations)", { timeout: 120_000 }, () => {
    let parsed = 0; // a report, or a refusal that came after reading the whole file
    for (let k = 0; k < 2800; k++) {
      const text = mutate(pick(fixtures));
      const spec = pick(specs);
      try {
        runPrognosis(text, spec, asOf);
        parsed += 1;
      } catch (e) {
        if (e instanceof GroupMismatchError) parsed += 1;
        if (!(e instanceof UploadError || e instanceof EvaluationError || e instanceof GroupMismatchError)) throw new Error(`crash on mutation ${k}: ${String(e)}`);
        expect((e as Error).message.length).toBeGreaterThan(10);
      }
    }
    expect(parsed).toBeGreaterThan(100); // most light mutations still parse
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });
});
