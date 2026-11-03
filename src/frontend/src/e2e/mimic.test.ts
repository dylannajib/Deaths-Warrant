/**
 * End-to-end tests on real FHIR: the 100 de-identified patients of the MIMIC-IV FHIR demo
 * (PhysioNet, ODbL), run through the exact browser pipeline (parse → extract → evaluate) for
 * every disease group. Build the data with `python -m deaths_warrant.sources.mimic_fhir_demo`;
 * without it (e.g. in CI) these tests are skipped. This checks real-world robustness and input
 * extraction, not accuracy: accuracy is validated per model on larger real datasets.
 *
 * MIMIC shifts dates into the 2100s, so each record is evaluated as of its own newest entry.
 */

import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { extractInputs, recordMatchesGroup } from "../engine/extract";
import { runPrognosis } from "../engine/prognosis";
import type { ModelSpec } from "../engine/spec";
import { latestDate, parseUpload } from "../parsing/upload";

const DATA = join(__dirname, "../../../../data/mimic_fhir_demo");
const BUNDLES = join(DATA, "bundles");
const available = existsSync(BUNDLES);
const specs = Object.values(
  import.meta.glob<ModelSpec>(["../../../models/*/spec.json", "!../../../models/_*/spec.json"], { eager: true, import: "default" }),
);
const ICD = {
  cancer: /^(C\d|1[4-9]\d|20[0-8])/, // malignant neoplasms (ICD-10 C, ICD-9 140-208)
  cardiovascular: /^(I(0[5-9]|1[13]|2\d|[3-5]\d|6\d|7[0-4])|39[3-8]|40[24]|4[1-3]\d|44[0-4])/,
  respiratory: /^(J4[0-7]|49[0-6])/,
} as const;

describe.skipIf(!available)("MIMIC-IV FHIR demo, end to end", () => {
  const files = available ? readdirSync(BUNDLES).filter((f) => f.endsWith(".json")) : [];

  it("finds all 100 patients", () => expect(files).toHaveLength(100));

  it("parses and evaluates every patient for every disease group", { timeout: 600_000 }, () => {
    const summary: Record<string, Record<string, number>> = {};
    let slowest = 0;
    const disagreements: string[] = [];
    for (const file of files) {
      const text = readFileSync(join(BUNDLES, file), "utf-8");
      const record = parseUpload(text, "2200-01-01");
      const asOf = latestDate(record)!;
      expect(asOf).toBeTruthy();
      const codes = record.conditions.flatMap((c) => c.codes.filter((x) => x.system === "icd9" || x.system === "icd10").map((x) => x.code));
      for (const spec of specs) {
        const started = performance.now();
        const report = runPrognosis(text, spec, asOf);
        slowest = Math.max(slowest, performance.now() - started);
        const r = report.result;
        const s = (summary[spec.id] ??= { patients: 0, groupMatch: 0, icdInGroup: 0, agreement: 0 });
        s.patients! += 1;

        // Sane numbers: survival falls over time, the range brackets the median.
        expect(r.survival_at["1"]).toBeGreaterThanOrEqual(r.survival_at["5"]!);
        for (let k = 1; k < r.curve.length; k++) expect(r.curve[k]![1]).toBeLessThanOrEqual(r.curve[k - 1]![1] + 1e-12);
        if (r.median_years !== null) {
          expect(r.median_years).toBeGreaterThan(0);
          expect(r.range_low_years!).toBeLessThanOrEqual(r.median_years);
          if (r.range_high_years !== null) expect(r.range_high_years).toBeGreaterThanOrEqual(r.median_years);
        }

        // Group detection agrees with an independent ICD check of the same record.
        const matched = recordMatchesGroup(spec, record);
        const byIcd = codes.some((c) => ICD[spec.id as keyof typeof ICD].test(c));
        s.groupMatch! += Number(matched);
        s.icdInGroup! += Number(byIcd);
        s.agreement! += Number(matched === byIcd);
        if (matched !== byIcd) {
          const hits = record.conditions.flatMap((c) => c.codes).filter((c) => (c.system === "snomed" || c.system === "icd9" || c.system === "icd10")).map((c) => `${c.system}:${c.code}`);
          disagreements.push(`${spec.id} ${file.slice(0, 8)} matched=${matched} icd=${byIcd} ${hits.filter((h) => /:(C|I|J|1[4-9]|20|39|4[0-4]|49)/.test(h)).slice(0, 12).join(" ")}`);
        }
        s[`layer:${r.layer.id}`] = (s[`layer:${r.layer.id}`] ?? 0) + Number(matched);
        if (matched) {
          const { observed } = extractInputs(spec, record, asOf);
          for (const [id, v] of Object.entries(observed)) {
            if (v !== null && v !== undefined && v !== false) s[`input:${id}`] = (s[`input:${id}`] ?? 0) + 1;
          }
        }
      }
    }
    writeFileSync(join(DATA, "e2e_disagreements.txt"), disagreements.join("\n"));
    for (const s of Object.values(summary)) expect(s.agreement).toBe(s.patients);
    expect(slowest).toBeLessThan(10_000);
    writeFileSync(join(DATA, "e2e_summary.json"), JSON.stringify({ slowestMs: Math.round(slowest), summary }, null, 1));
  });

  it("analyses a 50 MB record (the soft limit) in reasonable time", { timeout: 300_000 }, () => {
    // Real structure at scale: the largest demo record with its observations repeated.
    const largest = files.map((f) => join(BUNDLES, f)).sort((a, b) => readFileSync(b).length - readFileSync(a).length)[0]!;
    const bundle = JSON.parse(readFileSync(largest, "utf-8")) as { entry: { resource: { resourceType: string } }[] };
    const observations = bundle.entry.filter((e) => e.resource.resourceType === "Observation");
    const entries = [...bundle.entry];
    let size = JSON.stringify(bundle).length;
    const chunk = JSON.stringify(observations).length;
    while (size < 50e6) {
      entries.push(...observations);
      size += chunk;
    }
    const text = JSON.stringify({ ...bundle, entry: entries });
    const started = performance.now();
    const report = runPrognosis(text, specs.find((s) => s.id === "cardiovascular")!, latestDate(parseUpload(readFileSync(largest, "utf-8"), "2200-01-01"))!);
    const seconds = (performance.now() - started) / 1000;
    expect(report.result.median_years === null || report.result.median_years > 0).toBe(true);
    expect(seconds).toBeLessThan(60);
    writeFileSync(join(DATA, "e2e_large_file.json"), JSON.stringify({ megabytes: Math.round(text.length / 1e6), seconds: Math.round(seconds * 10) / 10 }));
  });
});
