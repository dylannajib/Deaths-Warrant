/**
 * FHIR (R4/R5) Bundle or Patient → PatientRecord. FHIR XML is first converted to the JSON
 * shape, so one reader serves both. Only the fields the models use are read. Everything else
 * (narrative HTML included) is ignored and never rendered.
 * Dates are left raw here and resolved afterwards (see upload.ts).
 */

import { RecordError } from "../errors";
import { INPATIENT_ACT_CODES, makeCode, type Code, type Condition, type Medication, type Observation, type PatientRecord } from "./record";
import { attr, type XmlElement } from "./xml";

type Json = unknown;
type Obj = Record<string, Json>;

export class FhirError extends RecordError {}

const isObj = (v: Json): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const arr = (v: Json): Json[] => (v === undefined || v === null ? [] : Array.isArray(v) ? v : [v]);
const objs = (v: Json): Obj[] => arr(v).filter(isObj);
const first = (v: Json): Json => arr(v)[0];
const str = (v: Json): string | undefined => (typeof v === "string" ? v : typeof v === "number" ? String(v) : undefined);
const num = (v: Json): number | undefined => {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : undefined;
};
const get = (o: Json, ...path: string[]): Json => {
  let cur: Json = o;
  for (const key of path) cur = isObj(cur) ? cur[key] : isObj(first(cur)) ? (first(cur) as Obj)[key] : undefined;
  return cur;
};

/** FHIR XML element → FHIR JSON shape (children become arrays, `value` attributes primitives). */
export function fhirXmlToJson(root: XmlElement): Obj {
  const convert = (el: XmlElement): Json => {
    const value = attr(el, "value");
    if (value !== undefined) return value; // primitive (any extensions on it are dropped)
    // No prototype: element names such as "__proto__" or "constructor" are just keys.
    const out: Obj = Object.create(null);
    for (const c of el.children) {
      if (c.local === "div") continue; // XHTML narrative: never needed, never rendered
      let v: Json;
      if ((c.local === "resource" || c.local === "contained") && c.children[0]) {
        const inner = c.children[0];
        v = { resourceType: inner.local, ...(convert(inner) as Obj) };
      } else {
        v = convert(c);
      }
      ((Object.hasOwn(out, c.local) ? out[c.local] : (out[c.local] = [])) as Json[]).push(v);
    }
    return out;
  };
  return { resourceType: root.local, ...(convert(root) as Obj) };
}

function codings(concept: Json): Code[] {
  const out: Code[] = [];
  for (const c of objs(get(concept, "coding"))) {
    const code = makeCode(str(first(c.system)), str(first(c.code)), str(first(c.display)));
    if (code) out.push(code);
  }
  return out;
}

const textOf = (concept: Json): string | undefined => str(first(get(concept, "text")));

const statusIs = (r: Obj, statuses: string[]) => statuses.includes(str(first(r.status)) ?? "");
const verification = (r: Obj): string | undefined => {
  const v = first(r.verificationStatus);
  return codings(v)[0]?.code ?? str(v);
};

// Classes in INPATIENT_ACT_CODES are hospital stays. Other classes (MIMIC records emergency
// admissions as EMER) count when the encounter records an admission and ends on a later day.

/** Start of the encounter if it was a hospital (inpatient) stay. */
function admissionStart(encounter: Obj | undefined): string | undefined {
  if (!encounter) return undefined;
  const start = str(first(get(encounter, "period", "start")));
  const end = str(first(get(encounter, "period", "end")));
  const classes = arr(encounter.class).flatMap((c) => [str(first(get(c, "code"))), ...codings(c).map((x) => x.code)]);
  const admitted = encounter.hospitalization !== undefined || encounter.admission !== undefined;
  const overnight = !!start && !!end && end.slice(0, 10) > start.slice(0, 10);
  return classes.some((c) => c !== undefined && INPATIENT_ACT_CODES.includes(c)) || (admitted && overnight) ? start : undefined;
}

function firstDate(...candidates: Json[]): string | undefined {
  for (const c of candidates) {
    const s = str(first(c));
    if (s) return s;
  }
  return undefined;
}

export function readFhir(doc: Json, format: "fhir-json" | "fhir-xml"): PatientRecord {
  if (!isObj(doc)) throw new FhirError("Not a FHIR resource");
  const type = str(doc.resourceType);
  let resources: Obj[];
  if (type === "Bundle") {
    resources = objs(doc.entry).map((e) => first(e.resource)).filter(isObj);
  } else if (type === "Patient") {
    resources = [doc];
  } else {
    throw new FhirError(`Expected a FHIR Bundle or Patient, found ${type ?? "no resourceType"}`);
  }

  const byRef = new Map<string, Obj>();
  if (type === "Bundle") {
    for (const e of objs(doc.entry)) {
      const r = first(e.resource);
      if (!isObj(r)) continue;
      const url = str(first(e.fullUrl));
      if (url) byRef.set(url, r);
      const id = str(first(r.id));
      if (id) byRef.set(`${str(r.resourceType)}/${id}`, r);
    }
  }

  const patients = resources.filter((r) => str(r.resourceType) === "Patient");
  const ids = new Set(patients.map((p) => str(first(p.id)) ?? p));
  if (ids.size === 0) throw new FhirError("The file contains no Patient resource");
  if (ids.size > 1) throw new FhirError("The file contains more than one patient; upload one patient's record");
  const patient = patients[0]!;

  const record: PatientRecord = { format, conditions: [], observations: [], medications: [], notes: [] };
  const birth = str(first(patient.birthDate));
  if (birth) record.birthDate = birth;
  const gender = str(first(patient.gender));
  if (gender === "female" || gender === "male") record.sex = gender;
  const country = objs(patient.address).map((a) => str(first(a.country))).find(Boolean);
  if (country) record.country = country;
  if (patient.deceasedBoolean === true || patient.deceasedBoolean === "true" || first(patient.deceasedDateTime)) {
    record.deceased = true;
  }

  // Encounter.diagnosis → Condition (R4 condition.reference, R5 condition[].reference.reference),
  // resolved like any other reference (resource type/id or the entry's fullUrl).
  const diagnosedIn = new Map<Obj, Obj>();
  for (const r of resources) {
    if (str(r.resourceType) !== "Encounter") continue;
    for (const d of objs(r.diagnosis)) {
      for (const c of objs(d.condition)) {
        const target = byRef.get(str(first(c.reference)) ?? str(get(c, "reference", "reference")) ?? "");
        if (target) diagnosedIn.set(target, r);
      }
    }
  }

  let datedByVisit = false;
  for (const r of resources) {
    switch (str(r.resourceType)) {
      case "Condition": {
        if (["refuted", "entered-in-error"].includes(verification(r) ?? "")) break;
        const c: Condition = { codes: codings(first(r.code)) };
        const text = textOf(first(r.code));
        if (text) c.text = text;
        const onset = firstDate(r.onsetDateTime, get(r, "onsetPeriod", "start"), r.recordedDate);
        // Encounter diagnoses (e.g. MIMIC-IV) carry no date of their own: use the visit's start.
        const visit = byRef.get(str(get(r, "encounter", "reference")) ?? "");
        const visitStart = onset ? undefined : firstDate(get(visit, "period", "start"));
        if (onset ?? visitStart) c.onset = (onset ?? visitStart)!;
        if (visitStart) datedByVisit = true;
        const admitted = admissionStart(visit) ?? admissionStart(diagnosedIn.get(r));
        if (admitted) c.admitted = admitted;
        if (c.codes.length || c.text) record.conditions.push(c);
        break;
      }
      case "Observation": {
        if (statusIs(r, ["entered-in-error", "cancelled"])) break;
        const date = firstDate(r.effectiveDateTime, get(r, "effectivePeriod", "start"), r.effectiveInstant, r.issued);
        record.observations.push(...observationsFrom(r, date));
        break;
      }
      case "MedicationRequest":
      case "MedicationStatement":
      case "MedicationAdministration":
      case "MedicationDispense": {
        if (statusIs(r, ["entered-in-error", "cancelled"])) break;
        let concept = first(r.medicationCodeableConcept) ?? get(r, "medication", "concept");
        const ref = str(get(r, "medicationReference", "reference")) ?? str(get(r, "medication", "reference", "reference"));
        if (!concept && ref) concept = first(byRef.get(ref)?.code);
        const m: Medication = { codes: codings(concept) };
        const text = textOf(concept);
        if (text) m.text = text;
        const date = firstDate(r.authoredOn, r.effectiveDateTime, get(r, "effectivePeriod", "start"), r.whenHandedOver);
        if (date) m.date = date;
        if (m.codes.length || m.text) record.medications.push(m);
        break;
      }
    }
  }
  if (datedByVisit) record.notes.push("Some diagnoses had no date of their own, so the start of the hospital visit they were recorded in was used.");
  return record;
}

function observationsFrom(r: Obj, date: string | undefined): Observation[] {
  const make = (codeConcept: Json, holder: Obj): Observation | undefined => {
    const o: Observation = { codes: codings(codeConcept) };
    const q = first(holder.valueQuantity);
    const value = num(first(get(q, "value"))) ?? num(first(holder.valueInteger)) ?? num(first(holder.valueDecimal));
    if (value !== undefined) {
      o.value = value;
      const unit = str(first(get(q, "code"))) ?? str(first(get(q, "unit")));
      if (unit) o.unit = unit;
    }
    const vc = first(holder.valueCodeableConcept);
    if (vc) {
      o.valueCodes = codings(vc);
      const t = textOf(vc);
      if (t) o.valueText = t;
    }
    const vs = str(first(holder.valueString));
    if (vs) o.valueText = vs;
    if (date) o.date = date;
    return o.codes.length ? o : undefined;
  };
  const out: Observation[] = [];
  const main = make(first(r.code), r);
  if (main && (main.value !== undefined || main.valueCodes || main.valueText)) out.push(main);
  for (const comp of objs(r.component)) {
    const o = make(first(comp.code), comp);
    if (o) out.push(o);
  }
  return out;
}
