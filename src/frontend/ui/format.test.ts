import { describe, expect, it } from "vitest";
import { chartEndYears, formatAssumed, formatDuration, formatPercent, formatRemaining, formatValue } from "./format";

describe("formatRemaining", () => {
  it("shows one decimal place", () => expect(formatRemaining(2.44, 20)).toEqual({ label: "Remaining years", value: "2.4" }));
  it("switches to months under a year", () => expect(formatRemaining(0.6, 20)).toEqual({ label: "Remaining months", value: "7" }));
  it("never shows zero months", () => expect(formatRemaining(0.01, 20).value).toBe("1"));
  it("caps beyond the reliable range", () => expect(formatRemaining(23, 20).value).toBe("20+"));
  it("caps beyond the horizon", () => expect(formatRemaining(null, 20).value).toBe("20+"));
});

describe("display helpers", () => {
  it("formats durations", () => {
    expect(formatDuration(0.5)).toBe("6 months");
    expect(formatDuration(0.05)).toBe("1 month");
    expect(formatDuration(4.46)).toBe("4.5 years");
    expect(formatDuration(null)).toBe("more than 60 years");
  });
  it("formats percentages with honest extremes", () => {
    expect(formatPercent(0.456)).toBe("46%");
    expect(formatPercent(0.001)).toBe("<1%");
    expect(formatPercent(0.999)).toBe(">99%");
  });
  it("formats input values", () => {
    expect(formatValue(42, "%")).toBe("42 %");
    expect(formatValue(1.25, "years")).toBe("1.3 years");
    expect(formatValue(true)).toBe("Yes");
    expect(formatValue("not_current")).toBe("not current");
    expect(formatValue(null)).toBe("—");
  });
  it("describes averaged inputs", () => {
    expect(formatAssumed([{ value: "female", weight: 1 }, { value: "male", weight: 3 }])).toBe("female 25%, male 75%");
  });
  it("ends the chart where survival becomes negligible", () => {
    expect(chartEndYears([[0, 1], [1, 0.5], [2.25, 0.01], [3, 0.001]])).toBe(5);
    expect(chartEndYears([[0, 1], [30, 0.6]])).toBe(30);
  });
});
