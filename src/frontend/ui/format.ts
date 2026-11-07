/** Display formatting shared by the result views. Pure functions, unit-tested. */

import { HORIZON_YEARS } from "../engine/evaluate";
import type { Value, WeightedValue } from "../engine/spec";

/** A duration as [number, unit]: years to one decimal, then months, weeks, days or hours. */
function durationParts(years: number): [string, string] {
  const days = years * 365.25;
  const whole = (n: number, unit: string): [string, string] => {
    const k = Math.max(1, Math.round(n));
    return [String(k), k === 1 ? unit : `${unit}s`];
  };
  if (years >= 1) return [years.toFixed(1), "years"];
  if (days >= 365.25 / 12) return whole(years * 12, "month");
  if (days >= 7) return whole(days / 7, "week");
  if (days >= 1) return whole(days, "day");
  return whole(days * 24, "hour");
}

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** The headline as [amount, label], e.g. ["4.5", "Years Left"]. ["20+", "Years Left"] beyond the reliable range. */
export function formatRemaining(medianYears: number | null, maxReliableYears: number): [string, string] {
  if (medianYears === null || medianYears > maxReliableYears) return [`${maxReliableYears}+`, "Years Left"];
  const [n, unit] = durationParts(medianYears);
  return [n, `${capitalise(unit)} Left`];
}

/** A duration in words: "4.5 years", "8 months", "2 weeks", or "more than 60 years". */
export function formatDuration(years: number | null): string {
  if (years === null) return `more than ${HORIZON_YEARS} years`;
  return durationParts(years).join(" ");
}

/** A range of durations: "1.8-4.9 years", "8 months-2.5 years", or "1.8 years or more". */
export function formatRange(low: number | null, high: number | null): string {
  if (high === null) return `${formatDuration(low)} or more`;
  if (low === null) return formatDuration(low);
  const [a, unitA] = durationParts(low);
  const [b, unitB] = durationParts(high);
  return unitA === unitB ? `${a}-${b} ${unitB}` : `${a} ${unitA}-${b} ${unitB}`;
}

/** Items in a sentence: "a", "a or b", "a, b or c" (with joiner "or"). Acronyms keep their capitals. */
export function listInWords(items: string[], joiner: "and" | "or"): string {
  const words = items.map((w) => (/^[A-Z][a-z]/.test(w) ? w.charAt(0).toLowerCase() + w.slice(1) : w));
  return words.length < 2 ? words.join("") : `${words.slice(0, -1).join(", ")} ${joiner} ${words.at(-1)}`;
}

/** A probability as a whole percentage, with "<1%" and ">99%" at the extremes. */
export function formatPercent(p: number): string {
  if (p < 0.005) return "<1%";
  if (p >= 0.995) return ">99%";
  return `${Math.round(p * 100)}%`;
}

/** An input value with its unit, e.g. "42 %", "Yes", "stage III". */
export function formatValue(value: Value | null, unit: string | null = null): string {
  if (value === null) return "Not recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    const n = Number.isInteger(value) ? String(value) : value.toFixed(1);
    return unit ? `${n} ${unit}` : n;
  }
  return value.replace(/_/g, " ");
}

/** How a missing input was averaged, e.g. "female (50%), male (50%)". */
export function formatAssumed(assumed: WeightedValue[], unit: string | null = null): string {
  const total = assumed.reduce((sum, w) => sum + w.weight, 0);
  return assumed.map((w) => `${formatValue(w.value, unit)} (${formatPercent(w.weight / total)})`).join(", ");
}

/** Where the survival chart's x-axis should end: when survival falls below 2%, at most 30 y. */
export function chartEndYears(curve: [number, number][]): number {
  const fall = curve.find(([, s]) => s < 0.02)?.[0] ?? curve.at(-1)?.[0] ?? 30;
  const nice = [2, 5, 10, 15, 20, 25, 30].find((y) => y >= fall) ?? 30;
  return nice;
}
