/**
 * Applies a spec's extraction rules to a parsed PatientRecord, producing the observed input
 * values plus a plain-language note of where each came from (shown in Reasoning).
 */

import { yearsBetween } from "../parsing/dates";
import type { Code, Observation, PatientRecord } from "../parsing/record";
import type { Observed } from "./evaluate";
import type { CodeSet, ExtractRule, ModelSpec, Value } from "./spec";

export interface Extraction {
  observed: Observed;
  /** input id → where the value came from, or why it is absent. */
  provenance: Record<string, string>;
}

export function matchesCodeSet(code: Code, set: CodeSet): boolean {
  switch (code.system) {
    case "icd10":
      return set.icd10.some((p) => code.code.startsWith(p));
    case "icd9":
      return set.icd9.some((p) => code.code.startsWith(p));
    case "snomed":
      return set.snomed.includes(code.code);
    default:
      return false;
  }
}

const describe = (c: Code) => `${c.system.toUpperCase()} ${c.code}${c.display ? ` (${c.display})` : ""}`;

function matchingConditions(record: PatientRecord, set: CodeSet) {
  return record.conditions.flatMap((cond) => {
    const hit = cond.codes.find((c) => matchesCodeSet(c, set));
    return hit ? [{ cond, hit }] : [];
  });
}

function latestObservation(record: PatientRecord, rule: { loinc: string[]; snomed: string[] }, asOf: string, maxAgeDays: number | null, accept: (o: Observation) => boolean) {
  let best: Observation | undefined;
  const wanted = (c: Code) => (c.system === "loinc" && rule.loinc.includes(c.code)) || (c.system === "snomed" && rule.snomed.includes(c.code));
  for (const o of record.observations) {
    if (!o.codes.some(wanted) || !accept(o)) continue;
    if (maxAgeDays !== null && (!o.date || yearsBetween(o.date, asOf) * 365.25 > maxAgeDays)) continue;
    if (!best || (o.date ?? "") > (best.date ?? "")) best = o;
  }
  return best;
}

function yearsSince(matches: ReturnType<typeof matchingConditions>, asOf: string): [Value | null, string] {
  const onsets = matches.map((m) => m.cond.onset).filter((d): d is string => !!d).sort();
  if (!onsets[0]) return [null, "No dated matching diagnosis"];
  return [Math.max(0, yearsBetween(onsets[0], asOf)), `Earliest matching diagnosis dated ${onsets[0]}`];
}

function apply(rule: ExtractRule, record: PatientRecord, asOf: string): [Value | null, string] {
  switch (rule.rule) {
    case "age": {
      if (!record.birthDate) return [null, "No birth date in the record"];
      return [yearsBetween(record.birthDate, asOf), `From birth date ${record.birthDate}`];
    }
    case "sex":
      return record.sex ? [record.sex, "From the patient's recorded sex"] : [null, "Sex not recorded as female or male"];
    case "observation_number": {
      const o = latestObservation(record, rule, asOf, rule.max_age_days, (x) => x.value !== undefined && (x.unit ?? "").toLowerCase() in rule.units);
      if (!o) return [null, "No usable measurement in the record"];
      const value = o.value! * rule.units[(o.unit ?? "").toLowerCase()]!;
      return [value, `Latest measurement: ${o.value} ${o.unit ?? ""}`.trim() + (o.date ? ` on ${o.date}` : "")];
    }
    case "observation_coded": {
      const key = (o: Observation) =>
        [...(o.valueCodes ?? []).map((c) => `${c.system}:${c.code}`), ...(o.valueText ? [`text:${o.valueText.trim().toLowerCase()}`] : [])].find((k) => k in rule.values);
      const o = latestObservation(record, rule, asOf, rule.max_age_days, (x) => key(x) !== undefined);
      if (!o) return [null, "Not recorded"];
      return [rule.values[key(o)!]!, `Recorded as ${o.valueCodes?.[0] ? describe(o.valueCodes[0]) : o.valueText}` + (o.date ? ` on ${o.date}` : "")];
    }
    case "condition_category": {
      for (const cat of rule.categories) {
        const m = matchingConditions(record, cat.codes)[0];
        if (m) return [cat.value, `Diagnosis ${describe(m.hit)}`];
      }
      return [null, "No matching diagnosis code in the record"];
    }
    case "condition_present": {
      const m = matchingConditions(record, rule.codes)[0];
      return m ? [true, `Diagnosis ${describe(m.hit)}`] : [false, "Not recorded (assumed absent)"];
    }
    case "condition_weighted_sum": {
      let total = 0;
      const hits: string[] = [];
      for (const g of rule.groups) {
        const m = matchingConditions(record, g.codes)[0];
        if (m) {
          total += g.weight;
          hits.push(`${describe(m.hit)} (+${g.weight})`);
        }
      }
      return [total, hits.length ? hits.join(", ") : "No qualifying conditions recorded (score 0)"];
    }
    case "years_since_condition":
      return yearsSince(matchingConditions(record, rule.codes), asOf);
    case "years_since_category": {
      const cat = rule.categories.find((c) => matchingConditions(record, c.codes).length);
      return cat ? yearsSince(matchingConditions(record, cat.codes), asOf) : [null, "No matching diagnosis"];
    }
    case "medication_present": {
      // A record with no medication list says nothing about treatment: unknown, not "not taken".
      if (!record.medications.length) return [null, "No medications in the record"];
      const names = rule.names.map((n) => n.toLowerCase());
      const m = record.medications.find(
        (med) =>
          med.codes.some((c) => (c.system === "rxnorm" && rule.rxnorm.includes(c.code)) || (c.system === "atc" && rule.atc.some((p) => c.code.startsWith(p)))) ||
          names.some((n) => [med.text, ...med.codes.map((c) => c.display)].some((t) => t?.toLowerCase().includes(n))),
      );
      return m ? [true, `Medication ${m.text ?? (m.codes[0] ? describe(m.codes[0]) : "")}`] : [false, "Not recorded (assumed not taken)"];
    }
    case "first_of": {
      let last: [Value | null, string] = [null, "Not recorded"];
      for (const r of rule.rules) {
        last = apply(r, record, asOf);
        if (last[0] !== null) return last;
      }
      return last;
    }
  }
}

export function extractInputs(spec: ModelSpec, record: PatientRecord, asOf: string): Extraction {
  const observed: Observed = {};
  const provenance: Record<string, string> = {};
  for (const input of spec.inputs) {
    const [value, note] = apply(input.extract, record, asOf);
    observed[input.id] = value;
    provenance[input.id] = note;
  }
  return { observed, provenance };
}

/** Does the record contain any diagnosis belonging to the chosen disease group? */
export function recordMatchesGroup(spec: ModelSpec, record: PatientRecord): boolean {
  return matchingConditions(record, spec.group_codes).length > 0;
}
