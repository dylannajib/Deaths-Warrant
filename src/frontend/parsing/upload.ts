/**
 * Upload entry point: untrusted text → validated PatientRecord.
 * The format is detected from content, never from the file name. Anything that is not a
 * FHIR Bundle/Patient (JSON or XML) or a C-CDA ClinicalDocument is rejected.
 */

import { readCcda } from "./ccda";
import { conventionForCountry, inferConvention, isAmbiguousFormat, parseDate, type Convention } from "./dates";
import { fhirXmlToJson, readFhir } from "./fhir";
import { RecordError } from "../errors";
import type { PatientRecord } from "./record";
import { MAX_DEPTH, parseXml } from "./xml";

export const SOFT_LIMIT_BYTES = 50 * 1024 * 1024;

export class UploadError extends RecordError {}

const FHIR_NS = "http://hl7.org/fhir";
const CDA_NS = "urn:hl7-org:v3";

function checkJsonDepth(value: unknown): void {
  const stack: [unknown, number][] = [[value, 1]];
  while (stack.length) {
    const [v, depth] = stack.pop()!;
    if (depth > MAX_DEPTH) throw new UploadError("The file is nested too deeply to be a patient record");
    if (typeof v === "object" && v !== null) {
      for (const child of Object.values(v)) stack.push([child, depth + 1]);
    }
  }
}

export function parseUpload(text: string, asOf: string): PatientRecord {
  const body = text.replace(/^﻿/, "");
  if (body.includes("\u0000")) throw new UploadError("This is not a text file. Upload a FHIR JSON, FHIR XML or C-CDA XML file.");
  const start = body.trimStart()[0];
  let record: PatientRecord;
  try {
    if (start === "{") {
      const doc: unknown = JSON.parse(body);
      checkJsonDepth(doc);
      record = readFhir(doc, "fhir-json");
    } else if (start === "<") {
      const root = parseXml(body);
      if (root.ns === FHIR_NS && (root.local === "Bundle" || root.local === "Patient")) {
        record = readFhir(fhirXmlToJson(root), "fhir-xml");
      } else if (root.ns === CDA_NS && root.local === "ClinicalDocument") {
        record = readCcda(root);
      } else {
        throw new UploadError("This XML file is not a FHIR Bundle/Patient or a C-CDA document.");
      }
    } else {
      throw new UploadError("Unrecognised file. Upload a FHIR JSON, FHIR XML or C-CDA XML file.");
    }
  } catch (e) {
    if (e instanceof UploadError) throw e;
    // Problems with the file become an UploadError. Anything else is a bug and propagates.
    if (e instanceof SyntaxError) throw new UploadError("Could not read the file: it is not valid JSON.");
    if (e instanceof RecordError) throw new UploadError(`Could not read the file: ${e.message}.`);
    throw e;
  }
  return resolveDates(record, asOf);
}

/** Convert every raw date to ISO, choosing a convention for ambiguous dd/mm vs mm/dd dates. */
function resolveDates(record: PatientRecord, asOf: string): PatientRecord {
  const raws = [record.birthDate, ...entryDates(record)].filter((d): d is string => !!d);

  const notes = [...record.notes];
  let convention: Convention = "dmy";
  if (raws.some(isAmbiguousFormat)) {
    const inferred = inferConvention(raws);
    const byCountry = conventionForCountry(record.country);
    convention = inferred ?? byCountry ?? "dmy";
    const label = convention === "dmy" ? "day/month/year" : "month/day/year";
    notes.push(
      inferred
        ? `Dates such as 03/04/2020 read as ${label}, the convention used elsewhere in the file.`
        : byCountry
          ? `Dates such as 03/04/2020 read as ${label}, the convention in ${record.country}.`
          : `Dates such as 03/04/2020 read as ${label}. The file does not indicate the convention.`,
    );
  }

  let invalid = 0;
  const fix = (raw: string | undefined): string | undefined => {
    if (!raw) return undefined;
    const iso = parseDate(raw, convention, asOf);
    if (!iso) invalid++;
    return iso;
  };
  const out: PatientRecord = { ...record, notes };
  const birth = fix(record.birthDate);
  if (birth) out.birthDate = birth;
  else delete out.birthDate;
  out.conditions = record.conditions.map((c) => withDate(withDate(c, "onset", fix(c.onset)), "admitted", fix(c.admitted)));
  out.observations = record.observations.map((o) => withDate(o, "date", fix(o.date)));
  out.medications = record.medications.map((m) => withDate(m, "date", fix(m.date)));
  if (invalid) notes.push(`${invalid} unreadable date(s) ignored.`);
  return out;
}

function withDate<T extends object, K extends keyof T & string>(item: T, key: K, iso: string | undefined): T {
  const copy = { ...item };
  if (iso) (copy as Record<string, unknown>)[key] = iso;
  else delete (copy as Record<string, unknown>)[key];
  return copy;
}

/** Every date on a record entry (diagnoses, hospital stays, observations, medications). */
function entryDates(record: PatientRecord): (string | undefined)[] {
  return [
    ...record.conditions.flatMap((c) => [c.onset, c.admitted]),
    ...record.observations.map((o) => o.date),
    ...record.medications.map((m) => m.date),
  ];
}

/** Newest dated entry in the record (used to warn when the record is stale). */
export function latestDate(record: PatientRecord): string | undefined {
  const dates = entryDates(record).filter((d): d is string => !!d);
  return dates.length ? dates.reduce((a, b) => (a > b ? a : b)) : undefined;
}
