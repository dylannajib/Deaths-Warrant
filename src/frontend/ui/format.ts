/** Display formatting shared by the result views. Pure functions, unit-tested. */

import { HORIZON_YEARS } from "../engine/evaluate";
import type { Value, WeightedValue } from "../engine/spec";

/** The headline: "Remaining years: X.X", months under a year, "20+" beyond the reliable range. */
export function formatRemaining(medianYears: number | null, maxReliableYears: number): { label: string; value: string } {
  if (medianYears === null || medianYears > maxReliableYears) {
    return { label: "Remaining years", value: `${maxReliableYears}+` };
  }
  if (medianYears < 1) {
    return { label: "Remaining months", value: String(Math.max(1, Math.round(medianYears * 12))) };
  }
  return { label: "Remaining years", value: medianYears.toFixed(1) };
}

/** A duration in words: "8 months", "4.5 years", or "more than 60 years". */
export function formatDuration(years: number | null): string {
  if (years === null) return `more than ${HORIZON_YEARS} years`;
  if (years < 1) {
    const months = Math.max(1, Math.round(years * 12));
    return `${months} month${months === 1 ? "" : "s"}`;
  }
  return `${years.toFixed(1)} years`;
}

/** A probability as a whole percentage, with "<1%" and ">99%" at the extremes. */
export function formatPercent(p: number): string {
  if (p < 0.005) return "<1%";
  if (p >= 0.995) return ">99%";
  return `${Math.round(p * 100)}%`;
}

/** An input value with its unit, e.g. "42 %", "Yes", "stage III". */
export function formatValue(value: Value | null, unit: string | null = null): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    const n = Number.isInteger(value) ? String(value) : value.toFixed(1);
    return unit ? `${n} ${unit}` : n;
  }
  return value.replace(/_/g, " ");
}

/** How a missing input was averaged, e.g. "female 50%, male 50%". */
export function formatAssumed(assumed: WeightedValue[], unit: string | null = null): string {
  const total = assumed.reduce((sum, w) => sum + w.weight, 0);
  return assumed.map((w) => `${formatValue(w.value, unit)} ${formatPercent(w.weight / total)}`).join(", ");
}

/** Where the survival chart's x-axis should end: when survival falls below 2%, at most 30 y. */
export function chartEndYears(curve: [number, number][]): number {
  const fall = curve.find(([, s]) => s < 0.02)?.[0] ?? curve.at(-1)?.[0] ?? 30;
  const nice = [2, 5, 10, 15, 20, 25, 30].find((y) => y >= fall) ?? 30;
  return nice;
}
