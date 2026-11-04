import { describe, expect, it } from "vitest";
import { attr, child, descendants, MAX_DEPTH, parseXml, XmlError } from "./xml";

describe("parseXml", () => {
  it("parses elements, attributes, namespaces, text, entities and CDATA", () => {
    const root = parseXml(`<?xml version="1.0"?>
      <!-- comment -->
      <ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <value xsi:type="PQ" value="1.5" unit="mg/dL"/>
        <title>A &amp; B &#x41;&#66; <![CDATA[<raw>]]></title>
      </ClinicalDocument>`);
    expect(root.local).toBe("ClinicalDocument");
    expect(root.ns).toBe("urn:hl7-org:v3");
    const value = child(root, "value")!;
    expect(attr(value, "type")).toBe("PQ");
    expect(value.ns).toBe("urn:hl7-org:v3");
    expect(child(root, "title")!.text).toBe("A & B AB <raw>");
  });

  it("resolves prefixed namespaces", () => {
    const root = parseXml(`<a xmlns:s="urn:x"><s:b/></a>`);
    expect(root.children[0]).toMatchObject({ local: "b", ns: "urn:x", name: "s:b" });
  });

  it.each([
    ["DOCTYPE (XXE)", `<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>`],
    ["entity declarations (billion laughs)", `<!ENTITY lol "lol"><a/>`],
    ["unknown entities", `<a>&lol;</a>`],
    ["bare ampersands", `<a>fish & chips</a>`],
    ["mismatched tags", `<a><b></a></b>`],
    ["unclosed tags", `<a><b>`],
    ["two roots", `<a/><b/>`],
    ["text outside the root", `oops<a/>`],
    ["unquoted attributes", `<a x=1/>`],
    ["duplicate attributes", `<a x="1" x="2"/>`],
    ["empty input", ``],
  ])("rejects %s", (_, xml) => {
    expect(() => parseXml(xml)).toThrow(XmlError);
  });

  it("rejects hostile nesting without overflowing the stack", () => {
    const deep = "<a>".repeat(MAX_DEPTH + 1) + "</a>".repeat(MAX_DEPTH + 1);
    expect(() => parseXml(deep)).toThrow(/nested too deeply/);
    const ok = "<a>".repeat(MAX_DEPTH) + "</a>".repeat(MAX_DEPTH);
    expect(parseXml(ok).local).toBe("a");
  });

  it("finds descendants in document order", () => {
    const root = parseXml(`<r><x id="1"><x id="2"/></x><y><x id="3"/></y></r>`);
    expect(descendants(root, "x").map((e) => attr(e, "id"))).toEqual(["1", "2", "3"]);
  });
});
