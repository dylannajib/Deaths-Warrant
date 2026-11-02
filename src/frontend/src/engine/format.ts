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
