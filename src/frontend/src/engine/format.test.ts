import { describe, expect, it } from "vitest";
import { formatRemaining } from "./format";

describe("formatRemaining", () => {
  it("shows one decimal place", () => expect(formatRemaining(2.44, 20)).toEqual({ label: "Remaining years", value: "2.4" }));
  it("switches to months under a year", () => expect(formatRemaining(0.6, 20)).toEqual({ label: "Remaining months", value: "7" }));
  it("never shows zero months", () => expect(formatRemaining(0.01, 20).value).toBe("1"));
  it("caps beyond the reliable range", () => expect(formatRemaining(23, 20).value).toBe("20+"));
  it("caps beyond the horizon", () => expect(formatRemaining(null, 20).value).toBe("20+"));
});
