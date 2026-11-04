/**
 * Date handling. Valid FHIR uses ISO 8601 and C-CDA uses HL7 TS (YYYYMMDD...), both
 * unambiguous. Non-conforming files may contain "03/04/50"-style dates. Those are resolved by
 * (1) the file's own convention, inferred from any date with a part above 12, else
 * (2) the patient's country (US => month first), else (3) day first, recorded as an assumption.
 * Two-digit years are placed in the century that keeps the date out of the future.
 */

export type Convention = "dmy" | "mdy";

const ISO = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?(?:T.*)?$/;
const HL7 = /^(\d{4})(?:(\d{2})(?:(\d{2})(?:\d{2,6}(?:\.\d+)?)?)?)?(?:[+-]\d{4})?$/;
const YMD_SLASH = /^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$/;
const AMBIGUOUS = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/;

const MONTH_FIRST_COUNTRIES = new Set(["us", "usa", "united states", "united states of america"]);

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function build(year: number, month: number, day: number): string | undefined {
  if (month < 1 || month > 12 || day < 1) return undefined;
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (day > daysInMonth) return undefined;
  return `${String(year).padStart(4, "0")}-${pad(month)}-${pad(day)}`;
}

/**
 * Partial dates take the middle of the period they name (YYYY => 1 July, YYYY-MM => the 15th),
 * which halves the worst-case error.
 */
function fromParts(y: string, m: string | undefined, d: string | undefined): string | undefined {
  return build(Number(y), m ? Number(m) : 7, d ? Number(d) : m ? 15 : 1);
}

export function isAmbiguousFormat(raw: string): boolean {
  return AMBIGUOUS.test(raw.trim());
}

/** Infer the convention from dates whose day part can only be one of the two fields. */
export function inferConvention(raws: Iterable<string>): Convention | undefined {
  let dmy = false;
  let mdy = false;
  for (const raw of raws) {
    const m = AMBIGUOUS.exec(raw.trim());
    if (!m) continue;
    if (Number(m[1]) > 12) dmy = true;
    if (Number(m[2]) > 12) mdy = true;
  }
  if (dmy !== mdy) return dmy ? "dmy" : "mdy";
  return undefined; // none, or contradictory
}

export function conventionForCountry(country: string | undefined): Convention | undefined {
  if (!country) return undefined;
  return MONTH_FIRST_COUNTRIES.has(country.trim().toLowerCase()) ? "mdy" : "dmy";
}

/** Parse any supported date string to YYYY-MM-DD, or undefined if it is not a valid date. */
export function parseDate(raw: string, convention: Convention, asOf: string): string | undefined {
  const s = raw.trim();
  let m = ISO.exec(s) ?? HL7.exec(s);
  if (m) return fromParts(m[1]!, m[2], m[3]);
  m = YMD_SLASH.exec(s);
  if (m) return build(Number(m[1]), Number(m[2]), Number(m[3]));
  m = AMBIGUOUS.exec(s);
  if (!m) return undefined;
  const [first, second] = [Number(m[1]), Number(m[2])];
  const [day, month] = convention === "dmy" ? [first, second] : [second, first];
  if (m[3]!.length === 4) return build(Number(m[3]), month, day);
  const yy = Number(m[3]);
  const modern = build(2000 + yy, month, day);
  if (modern && modern <= asOf) return modern;
  return build(1900 + yy, month, day);
}

/** Whole and fractional years between two ISO dates. */
export function yearsBetween(from: string, to: string): number {
  return (Date.parse(to) - Date.parse(from)) / (365.25 * 24 * 3600 * 1000);
}
