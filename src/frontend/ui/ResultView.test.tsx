import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import fixture from "../../prognosis-models/_fixture/spec.json";
import { evaluate } from "../engine/evaluate";
import type { PrognosisReport } from "../engine/prognosis";
import type { ModelSpec } from "../engine/spec";
import { ResultView } from "./ResultView";

const spec = fixture as unknown as ModelSpec;

function report(observed: Record<string, number | string | boolean>, overrides: Partial<PrognosisReport> = {}): PrognosisReport {
  const result = evaluate(spec, observed);
  const layer = spec.layers.find((l) => l.id === result.layer.id)!;
  return {
    format: "fhir-json",
    asOf: "2026-11-03",
    result,
    provenance: Object.fromEntries(spec.inputs.map((i) => [i.id, `from test ${i.id}`])),
    warnings: [],
    notes: [],
    model: {
      id: spec.id, name: spec.name, version: spec.version, description: spec.description,
      max_reliable_years: spec.max_reliable_years,
      layer: { label: layer.label, description: layer.description, sources: layer.sources, kind: "hazard" },
      inputs: Object.fromEntries(spec.inputs.map((i) => [i.id, { label: i.label, unit: null, source: null }])),
      sources: [{ id: "s1", citation: "A published source.", url: "https://example.org/", licence: "CC BY 4.0" }],
      validation: [],
    },
    ...overrides,
  };
}

describe("ResultView", () => {
  it("shows the headline, both dropdowns and what was read", () => {
    const html = renderToStaticMarkup(<ResultView report={report({ age: 60, score: 4, flag: false })} />);
    expect(html).toContain('<p class="headline"><span class="amount">3.5</span><span class="label">Years Left</span></p>');
    expect(html).toContain("<th scope=\"col\">25-75% range</th>");
    expect(html).toContain("See More</span></button>");
    expect(html).toContain("Reasoning</span></button>");
    expect(html).toContain("from test score");
    expect(html).toContain("A published source.");
    expect(html).toContain("No validation results published");
    expect(html).toContain("<svg"); // survival chart
  });

  it("explains averaged inputs, skipped layers and warnings", () => {
    const html = renderToStaticMarkup(
      <ResultView report={report({ age: 60, sex: "male" }, { warnings: ["No fixture diagnosis was found."] })} />,
    );
    expect(html).toContain("No fixture diagnosis was found.");
    expect(html).toContain("Averaged: 2 (50%), 6 (50%)");
    expect(html).toContain("<em>Points</em> could not be used because the record has no score or kind.");
  });

  it("shows 20+ with the computed value when beyond the reliable range", () => {
    const r = report({ age: 0, sex: "female" });
    const html = renderToStaticMarkup(<ResultView report={{ ...r, model: { ...r.model, max_reliable_years: 10 }, result: { ...r.result, beyond_reliable: true } }} />);
    expect(html).toContain('<span class="amount">10+</span><span class="label">Years Left</span>');
    expect(html).toContain("Computed median: 11.6 years");
  });

  it("uses no semicolons or em dashes in its own text", () => {
    const text = renderToStaticMarkup(<ResultView report={report({ age: 60, sex: "male" })} />).replace(/<[^>]+>|&[#a-z0-9]+;/gi, " "); // tags and HTML entities
    expect(text).not.toMatch(/[;—]/);
  });

  it("shows text from the uploaded file as text, never as HTML", () => {
    const evil = `<img src=x onerror="alert(1)"><script>alert(2)</script>`;
    const r = report({ age: 60, score: 4, flag: false });
    const html = renderToStaticMarkup(<ResultView report={{ ...r, provenance: { ...r.provenance, score: evil }, notes: [evil] }} />);
    expect(html).not.toContain("<img src=x");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
});
