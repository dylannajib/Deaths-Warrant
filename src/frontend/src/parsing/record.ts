/** Format-independent patient record: what every parser (FHIR JSON/XML, C-CDA) produces. */

export type CodeSystem = "icd10" | "icd9" | "snomed" | "loinc" | "rxnorm" | "atc" | "other";

export interface Code {
  system: CodeSystem;
  /** Normalised: ICD upper-case without dots, others as recorded. */
  code: string;
  display?: string;
}

export interface Condition {
  codes: Code[];
  text?: string;
  /** ISO date (YYYY-MM-DD) once dates are resolved. */
  onset?: string;
  /** Start of the hospital (inpatient) stay this diagnosis was recorded in, if any. */
  admitted?: string;
}

export interface Observation {
  codes: Code[];
  value?: number;
  unit?: string;
  valueCodes?: Code[];
  valueText?: string;
  date?: string;
}

export interface Medication {
  codes: Code[];
  text?: string;
  date?: string;
}

/** HL7 v3 ActCode encounter classes that mean a hospital (inpatient) stay. */
export const INPATIENT_ACT_CODES: readonly string[] = ["IMP", "ACUTE", "NONAC", "SS"];

export type SourceFormat = "fhir-json" | "fhir-xml" | "ccda";

export interface PatientRecord {
  format: SourceFormat;
  birthDate?: string;
  sex?: "female" | "male";
  country?: string;
  deceased?: boolean;
  conditions: Condition[];
  observations: Observation[];
  medications: Medication[];
  /** Assumptions made while reading the file, shown in Reasoning. */
  notes: string[];
}

const OID: Record<string, CodeSystem> = {
  "2.16.840.1.113883.6.96": "snomed",
  "2.16.840.1.113883.6.1": "loinc",
  "2.16.840.1.113883.6.90": "icd10", // ICD-10-CM
  "2.16.840.1.113883.6.3": "icd10", // ICD-10 (WHO)
  "2.16.840.1.113883.6.103": "icd9", // ICD-9-CM diagnoses
  "2.16.840.1.113883.6.2": "icd9",
  "2.16.840.1.113883.6.88": "rxnorm",
  "2.16.840.1.113883.6.73": "atc",
};

/** Map a FHIR system URI or CDA OID to a code system. Procedure code systems map to "other". */
export function normaliseSystem(system: string | undefined): CodeSystem {
  if (!system) return "other";
  const s = system.trim().toLowerCase().replace(/^urn:oid:/, "");
  if (s in OID) return OID[s]!;
  if (/pcs|proc/.test(s)) return "other";
  if (s.includes("snomed")) return "snomed";
  if (s.includes("loinc")) return "loinc";
  if (/icd-?10/.test(s)) return "icd10";
  if (/icd-?9/.test(s)) return "icd9";
  if (s.includes("rxnorm")) return "rxnorm";
  if (/(^|[/.])atc($|[/.])/.test(s) || s.includes("whocc")) return "atc";
  return "other";
}

export function makeCode(system: string | undefined, code: string | undefined, display?: string): Code | undefined {
  const raw = code?.trim();
  if (!raw) return undefined;
  const sys = normaliseSystem(system);
  const normalised = sys === "icd10" || sys === "icd9" ? raw.toUpperCase().replace(/[.\s]/g, "") : raw;
  const out: Code = { system: sys, code: normalised };
  const d = display?.trim();
  if (d) out.display = d;
  return out;
}
