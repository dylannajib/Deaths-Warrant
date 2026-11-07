import { describe, expect, it } from "vitest";
import { chartEndYears, formatAssumed, formatDuration, formatPercent, formatRange, formatRemaining, formatValue, listInWords } from "./format";

describe("formatRemaining", () => {
  const r = (median: number | null) => ({ median_years: median, beyond_reliable: median === null || median > 20 });
  it("shows years to one decimal place", () => expect(formatRemaining(r(2.44), 20)).toEqual(["2.4", "years left"]));
  it("switches to months under a year", () => expect(formatRemaining(r(0.6), 20)).toEqual(["7", "months left"]));
  it("switches to weeks under a month", () => expect(formatRemaining(r(14 / 365.25), 20)).toEqual(["2", "weeks left"]));
  it("switches to days under a week", () => expect(formatRemaining(r(1 / 365.25), 20)).toEqual(["1", "day left"]));
  it("switches to hours under a day", () => expect(formatRemaining(r(0.25 / 365.25), 20)).toEqual(["6", "hours left"]));
  it("caps beyond the reliable range", () => expect(formatRemaining(r(23), 20)).toEqual(["20+", "years left"]));
  it("caps beyond the horizon", () => expect(formatRemaining(r(null), 20)).toEqual(["20+", "years left"]));
});

describe("display helpers", () => {
  it("formats durations", () => {
    expect(formatDuration(0.5)).toBe("6 months");
    expect(formatDuration(0.05)).toBe("3 weeks");
    expect(formatDuration(4.46)).toBe("4.5 years");
    expect(formatDuration(null)).toBe("more than 60 years");
  });
  it("formats ranges", () => {
    expect(formatRange(1.84, 4.9)).toBe("1.8-4.9 years");
    expect(formatRange(0.5, 2.46)).toBe("6 months-2.5 years");
    expect(formatRange(1.8, null)).toBe("1.8 years or more");
  });
  it("lists items in a sentence", () => {
    expect(listInWords(["Left ventricular ejection fraction"], "or")).toBe("left ventricular ejection fraction");
    expect(listInWords(["NYHA class", "Age", "Sex"], "and")).toBe("NYHA class, age and sex");
    expect(listInWords(["Score", "Kind"], "or")).toBe("score or kind");
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
    expect(formatValue(null)).toBe("Not recorded");
  });
  it("describes averaged inputs", () => {
    expect(formatAssumed([{ value: "female", weight: 1 }, { value: "male", weight: 3 }])).toBe("female (25%), male (75%)");
  });
  it("ends the chart where survival becomes negligible", () => {
    expect(chartEndYears([[0, 1], [1, 0.5], [2.25, 0.01], [3, 0.001]])).toBe(5);
    expect(chartEndYears([[0, 1], [30, 0.6]])).toBe(30);
  });
});
