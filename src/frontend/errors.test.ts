import { describe, expect, it, vi } from "vitest";
import { describeFailure, RecordError } from "./errors";
import { ISSUES_URL } from "./links";
import { XmlError } from "./parsing/xml";
import { parseUpload, UploadError } from "./parsing/upload";

describe("describeFailure", () => {
  it("shows a problem with the record as is", () => {
    expect(describeFailure(new UploadError("The file contains no Patient resource"))).toBe("The file contains no Patient resource");
  });

  it("reports anything else as a bug, with where it happened", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const bug = new TypeError("Cannot read properties of undefined (reading 'code')");
    bug.stack = "TypeError: Cannot read properties of undefined\n    at readFhir (src/parsing/fhir.ts:142:7)\n    at parseUpload (src/parsing/upload.ts:40:16)";
    const message = describeFailure(bug);
    expect(message).toMatch(/a bug, not a problem with your file/);
    expect(message).toContain(ISSUES_URL);
    expect(message).toContain("TypeError: Cannot read properties of undefined (reading 'code') at readFhir (src/parsing/fhir.ts:142:7)");
    expect(log).toHaveBeenCalledWith("Death's Warrant internal error:", bug);
    log.mockRestore();
  });

  it("names the failing stage", () => {
    expect(new XmlError("x").name).toBe("XmlError");
    expect(new XmlError("x")).toBeInstanceOf(RecordError);
  });
});

describe("parseUpload error kinds", () => {
  it("turns a parser's record error into an UploadError that says why", () => {
    expect(() => parseUpload("<Patient xmlns='http://hl7.org/fhir'><a></b></Patient>", "2026-11-04")).toThrow(UploadError);
    expect(() => parseUpload("{ not json", "2026-11-04")).toThrow(/not valid JSON/);
  });
});
