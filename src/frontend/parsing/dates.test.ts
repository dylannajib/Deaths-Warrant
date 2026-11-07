import { describe, expect, it } from "vitest";
import { conventionForCountry, formatDate, inferConvention, parseDate, yearsBetween } from "./dates";

const asOf = "2026-11-02";

describe("formatDate", () => {
  it("shows day month year", () => {
    expect(formatDate("2026-11-01")).toBe("1 Nov 2026");
    expect(formatDate("2025-02-28T13:45:00Z")).toBe("28 Feb 2025");
    expect(formatDate("not a date")).toBe("not a date");
  });
});

describe("parseDate", () => {
  it.each([
    ["1950-03-04", "1950-03-04"],
    ["1950-03-04T10:00:00+10:00", "1950-03-04"],
    ["1950", "1950-07-01"],
    ["1950-03", "1950-03-15"],
    ["19500304", "1950-03-04"],
    ["195003041230+1000", "1950-03-04"],
    ["1950/03/04", "1950-03-04"],
  ])("reads unambiguous %s", (raw, iso) => expect(parseDate(raw, "mdy", asOf)).toBe(iso));

  it("applies the convention to ambiguous dates", () => {
    expect(parseDate("03/04/1950", "dmy", asOf)).toBe("1950-04-03");
    expect(parseDate("03/04/1950", "mdy", asOf)).toBe("1950-03-04");
  });

  it("keeps two-digit years out of the future", () => {
    expect(parseDate("03/04/50", "dmy", asOf)).toBe("1950-04-03");
    expect(parseDate("03/04/24", "dmy", asOf)).toBe("2024-04-03");
    expect(parseDate("31/12/26", "dmy", asOf)).toBe("1926-12-31");
  });

  it.each(["31/02/2020", "2020-13-01", "yesterday", "13/13/2020"])("rejects invalid %s", (raw) =>
    expect(parseDate(raw, "dmy", asOf)).toBeUndefined(),
  );
});

describe("convention", () => {
  it("is inferred from a day above 12", () => {
    expect(inferConvention(["03/04/2020", "25/12/2019"])).toBe("dmy");
    expect(inferConvention(["03/04/2020", "12/25/2019"])).toBe("mdy");
    expect(inferConvention(["03/04/2020"])).toBeUndefined();
    expect(inferConvention(["25/12/2019", "12/25/2019"])).toBeUndefined();
  });

  it("falls back to the patient's country", () => {
    expect(conventionForCountry("US")).toBe("mdy");
    expect(conventionForCountry("Australia")).toBe("dmy");
    expect(conventionForCountry(undefined)).toBeUndefined();
  });
});

it("measures years between dates", () => {
  expect(yearsBetween("2000-01-01", "2010-01-01")).toBeCloseTo(10, 2);
});
