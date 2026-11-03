/**
 * C-CDA R2.x ClinicalDocument → PatientRecord.
 * Problems come from Problem Observations (templateId ...22.4.4) wherever they appear.
 * Results and vital signs come from any other observation coded in LOINC, medications from
 * substanceAdministration entries other than Immunization Activities (vaccines are not
 * treatment). Negated entries (negationInd="true") are skipped. A problem recorded during a
 * hospital stay (inside an inpatient Encounter Activity, or a discharge summary's hospital
 * admission/discharge diagnosis) also carries the stay's start date.
 * Dates are left raw here and resolved afterwards (see upload.ts).
 */

import { RecordError } from "../errors";
import { INPATIENT_ACT_CODES, makeCode, type Code, type Observation, type PatientRecord } from "./record";
import { attr, child, children, descendants, type XmlElement } from "./xml";

const PROBLEM_OBSERVATION = "2.16.840.1.113883.10.20.22.4.4";
const IMMUNIZATION_ACTIVITY = "2.16.840.1.113883.10.20.22.4.52";
const ENCOUNTER_ACTIVITY = "2.16.840.1.113883.10.20.22.4.49";
const HOSPITAL_DIAGNOSIS = ["2.16.840.1.113883.10.20.22.4.33", "2.16.840.1.113883.10.20.22.4.34"]; // discharge, admission
const ACT_CODE = "2.16.840.1.113883.5.4";
const CPT = "2.16.840.1.113883.6.12";
const SNOMED = "2.16.840.1.113883.6.96";
const INPATIENT_CPT = /^992(2[1-6]|3[1-9])$/; // hospital inpatient and observation care
const INPATIENT_SNOMED = ["32485007", "8715000", "183452005"]; // hospital admission (any, elective, emergency)

export class CcdaError extends RecordError {}

function codesOf(el: XmlElement | undefined): Code[] {
  if (!el || attr(el, "nullFlavor") && !attr(el, "code")) {
    return el ? children(el, "translation").flatMap(codesOf) : [];
  }
  const own = makeCode(attr(el, "codeSystem"), attr(el, "code"), attr(el, "displayName"));
  return [...(own ? [own] : []), ...children(el, "translation").flatMap(codesOf)];
}

function textOf(el: XmlElement | undefined): string | undefined {
  const t = el && (child(el, "originalText")?.text ?? el.text);
  return t?.trim() || undefined;
}

function dateOf(el: XmlElement): string | undefined {
  const eff = child(el, "effectiveTime");
  if (!eff) return undefined;
  return attr(eff, "value") ?? attr(child(eff, "low") ?? eff, "value") ?? undefined;
}

function isInpatient(code: XmlElement | undefined): boolean {
  return !!code && [code, ...children(code, "translation")].some((c) => {
    const system = attr(c, "codeSystem");
    const value = attr(c, "code") ?? "";
    return (system === ACT_CODE && INPATIENT_ACT_CODES.includes(value)) || (system === CPT && INPATIENT_CPT.test(value)) ||
      (system === SNOMED && INPATIENT_SNOMED.includes(value));
  });
}

/** Problem observation → start of the hospital stay it was recorded in. */
function hospitalStays(root: XmlElement, body: XmlElement): Map<XmlElement, string> {
  const out = new Map<XmlElement, string>();
  const mark = (holder: XmlElement, start: string | undefined) => {
    if (start) for (const obs of descendants(holder, "observation")) out.set(obs, start);
  };
  for (const enc of descendants(body, "encounter")) {
    if (templateIds(enc).includes(ENCOUNTER_ACTIVITY) && isInpatient(child(enc, "code"))) mark(enc, dateOf(enc));
  }
  const componentOf = child(root, "componentOf");
  const stay = componentOf && child(componentOf, "encompassingEncounter");
  const stayStart = stay && dateOf(stay);
  for (const act of descendants(body, "act")) {
    if (templateIds(act).some((t) => t !== undefined && HOSPITAL_DIAGNOSIS.includes(t))) mark(act, stayStart);
  }
  return out;
}

const negated = (el: XmlElement) => attr(el, "negationInd") === "true";
const templateIds = (el: XmlElement) => children(el, "templateId").map((t) => attr(t, "root"));

export function readCcda(root: XmlElement): PatientRecord {
  const record: PatientRecord = { format: "ccda", conditions: [], observations: [], medications: [], notes: [] };
  const targets = children(root, "recordTarget");
  if (targets.length !== 1) {
    throw new CcdaError(targets.length ? "The document covers more than one patient" : "The document has no patient (recordTarget)");
  }
  const role = child(targets[0]!, "patientRole");
  const patient = role && child(role, "patient");
  if (patient) {
    const birth = attr(child(patient, "birthTime") ?? patient, "value");
    if (birth && child(patient, "birthTime")) record.birthDate = birth;
    const gender = attr(child(patient, "administrativeGenderCode") ?? patient, "code");
    if (gender === "F") record.sex = "female";
    if (gender === "M") record.sex = "male";
    if (child(patient, "deceasedInd") && attr(child(patient, "deceasedInd")!, "value") === "true") record.deceased = true;
  }
  const country = role && children(role, "addr").map((a) => child(a, "country")?.text.trim()).find(Boolean);
  if (country) record.country = country;

  const body = child(root, "component") ?? root;
  const stays = hospitalStays(root, body);
  for (const obs of descendants(body, "observation")) {
    if (negated(obs)) continue;
    const date = dateOf(obs);
    if (templateIds(obs).includes(PROBLEM_OBSERVATION)) {
      const value = child(obs, "value");
      const codes = codesOf(value);
      const text = textOf(value);
      if (!codes.length && !text) continue;
      const condition: PatientRecord["conditions"][number] = { codes };
      if (text) condition.text = text;
      if (date) condition.onset = date;
      const admitted = stays.get(obs);
      if (admitted) condition.admitted = admitted;
      record.conditions.push(condition);
      continue;
    }
    const codes = codesOf(child(obs, "code"));
    if (!codes.some((c) => c.system === "loinc")) continue;
    const o: Observation = { codes };
    const value = child(obs, "value");
    if (value) {
      const type = attr(value, "type");
      if (type === "PQ" || type === "INT" || type === "REAL") {
        const n = Number(attr(value, "value"));
        if (Number.isFinite(n) && attr(value, "value")?.trim()) {
          o.value = n;
          const unit = attr(value, "unit");
          if (unit) o.unit = unit;
        }
      } else if (type === "CD" || type === "CE" || type === "CO" || type === "CV") {
        o.valueCodes = codesOf(value);
        const t = textOf(value);
        if (t) o.valueText = t;
      } else if (type === "ST" && value.text.trim()) {
        o.valueText = value.text.trim();
      }
    }
    if (date) o.date = date;
    if (o.value !== undefined || o.valueCodes?.length || o.valueText) record.observations.push(o);
  }

  for (const sa of descendants(body, "substanceAdministration")) {
    if (negated(sa) || templateIds(sa).includes(IMMUNIZATION_ACTIVITY)) continue;
    const material = descendants(sa, "manufacturedMaterial")[0];
    const codeEl = material && child(material, "code");
    const codes = codesOf(codeEl);
    const text = textOf(codeEl) ?? material?.children.find((c) => c.local === "name")?.text.trim();
    if (!codes.length && !text) continue;
    const med: PatientRecord["medications"][number] = { codes };
    if (text) med.text = text;
    const date = dateOf(sa);
    if (date) med.date = date;
    record.medications.push(med);
  }
  return record;
}
