/** The headline, warnings, and the "See More" and "Reasoning" dropdowns for one report. */

import { useLayoutEffect, useRef } from "react";
import type { PrognosisReport } from "../engine/prognosis";
import type { Source, ValidationResult } from "../engine/spec";
import { Dropdown } from "./Dropdown";
import { formatDate } from "../parsing/dates";
import { formatAssumed, formatDuration, formatPercent, formatRange, formatRemaining, formatValue, listInWords } from "./format";
import { SurvivalChart } from "./SurvivalChart";

const FORMAT_LABEL = { "fhir-json": "FHIR JSON", "fhir-xml": "FHIR XML", ccda: "C-CDA" } as const;

export function ResultView({ report }: { report: PrognosisReport }) {
  return (
    <section className="result" aria-label="Your result">
      <Headline parts={formatRemaining(report.result.median_years, report.model.max_reliable_years)} />
      {report.warnings.length > 0 && (
        <ul className="warnings">
          {report.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <Dropdown className="drop" title="See More">
        <SeeMore report={report} />
      </Dropdown>
      <Dropdown className="drop" title="Reasoning">
        <Reasoning report={report} />
      </Dropdown>
    </section>
  );
}

/** Gap between the amount and its label, as a share of the label's font size. */
const HEADLINE_GAP_EM = 0.45;

/**
 * Fit a one-line span's box to its visible glyphs, and centre those glyphs in it.
 * Fonts leave uneven space around their glyphs (Beth Ellen and italics most of all), so
 * without this the gap and centring between the amount and its label vary with the text.
 */
function fitToGlyphs(el: HTMLElement): void {
  el.style.margin = el.style.transform = "";
  const ctx = document.createElement("canvas").getContext("2d");
  if (!ctx) return;
  const cs = getComputedStyle(el);
  ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  const m = ctx.measureText(el.textContent ?? "");
  const height = el.getBoundingClientRect().height;
  const baseline = (height - m.fontBoundingBoxAscent - m.fontBoundingBoxDescent) / 2 + m.fontBoundingBoxAscent;
  el.style.marginTop = `${m.actualBoundingBoxAscent - baseline}px`;
  el.style.marginBottom = `${baseline + m.actualBoundingBoxDescent - height}px`;
  el.style.transform = `translateX(${(m.width - m.actualBoundingBoxRight + m.actualBoundingBoxLeft) / 2}px)`;
}

/** The amount above its label: visibly centred, with the same gap whatever the text. */
function Headline({ parts: [amount, label] }: { parts: [string, string] }) {
  const amountRef = useRef<HTMLSpanElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const fit = () => {
      const a = amountRef.current;
      const l = labelRef.current;
      if (!a || !l) return;
      fitToGlyphs(a);
      fitToGlyphs(l);
      const gap = HEADLINE_GAP_EM * parseFloat(getComputedStyle(l).fontSize);
      l.style.marginTop = `${parseFloat(l.style.marginTop) + gap}px`;
    };
    fit();
    void document.fonts.ready.then(fit); // glyph sizes change once the web fonts arrive
    window.addEventListener("resize", fit); // the amount's size follows the window width
    return () => window.removeEventListener("resize", fit);
  }, [amount, label]);
  return (
    <p className="headline">
      <span ref={amountRef} className="amount">
        {amount}
      </span>
      <span ref={labelRef} className="label">
        {label}
      </span>
    </p>
  );
}

function SeeMore({ report }: { report: PrognosisReport }) {
  const r = report.result;
  return (
    <div className="drop-body">
      <table className="table even">
        <caption>Estimated time left</caption>
        <thead>
          <tr>
            <th scope="col">Median survival</th>
            <th scope="col">25-75% range</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{formatDuration(r.median_years)}</td>
            <td>{formatRange(r.range_low_years, r.range_high_years)}</td>
          </tr>
        </tbody>
      </table>
      <SurvivalChart curve={r.curve} medianYears={r.median_years} />
      <table className="table even">
        <caption>Probability of survival</caption>
        <thead>
          <tr>
            {Object.keys(r.survival_at).map((t) => (
              <th key={t} scope="col">
                {t} year{t === "1" ? "" : "s"}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            {Object.entries(r.survival_at).map(([t, s]) => (
              <td key={t}>{formatPercent(s)}</td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function Reasoning({ report }: { report: PrognosisReport }) {
  const { result, model, provenance } = report;
  const used = result.inputs.filter((i) => i.status !== "unused");
  const label = (id: string) => model.inputs[id]?.label ?? id;
  return (
    <div className="drop-body reasoning">
      <h3>Model</h3>
      <p>
        <strong>{model.layer.label}</strong>. {model.name} model, version {model.version}.
      </p>
      <p>{model.layer.description}</p>
      {result.skipped_layers.map((l) => (
        <p key={l.id}>
          <em>{l.label}</em> could not be used because the record has no {listInWords(l.lacking.map(label), "or")}.
        </p>
      ))}
      {result.beyond_reliable && (
        <p>
          Computed median: {formatDuration(result.median_years)}. Estimates above {model.max_reliable_years} years are
          extrapolated and shown as {model.max_reliable_years}+.
        </p>
      )}

      <h3>Inputs read from the record</h3>
      <table className="table inputs">
        <thead>
          <tr>
            <th scope="col">Input</th>
            <th scope="col">Value</th>
            <th scope="col">Source</th>
          </tr>
        </thead>
        <tbody>
          {used.map((i) => {
            const unit = model.inputs[i.id]?.unit ?? null;
            let where = provenance[i.id] ?? "";
            if (i.status === "implausible") where += ". Outside the plausible range, ignored";
            if (i.assumed && i.status === "missing") where += ". Averaged over published population data";
            return (
              <tr key={i.id}>
                <th scope="row">{label(i.id)}</th>
                <td>{i.assumed ? `Averaged: ${formatAssumed(i.assumed, unit)}` : formatValue(i.value, unit)}</td>
                <td>{where}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <Terms report={report} label={label} />

      <h3>Assumptions</h3>
      <ul>
        <li>Date of estimate: {formatDate(report.asOf)}.</li>
        <li>File format: {FORMAT_LABEL[report.format]}.</li>
        <li>Population mortality: United States life tables, by age and sex.</li>
        <li>Missing inputs are averaged over published population data. This widens the range.</li>
        {report.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>

      <h3>Sources</h3>
      <SourceList sources={model.sources} used={model.layer.sources} />

      <h3>Model's current accuracy</h3>
      <Validation results={model.validation} />
    </div>
  );
}

function Terms({ report, label }: { report: PrognosisReport; label: (id: string) => string }) {
  const { terms } = report.result;
  if (!terms.length) return null;
  const points = report.model.layer.kind === "points";
  return (
    <>
      <h3>{points ? "Score points" : "Risk multipliers"}</h3>
      <table className="table even">
        <tbody>
          {terms.map((t, k) => (
            <tr key={`${t.input}-${k}`}>
              <th scope="row">{label(t.input)}</th>
              <td>
                {t.contribution === null
                  ? "Not recorded, averaged"
                  : points
                    ? `${t.contribution} point${t.contribution === 1 ? "" : "s"}`
                    : `× ${Math.exp(t.contribution).toFixed(2)} mortality`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function SourceList({ sources, used }: { sources: Source[]; used: string[] }) {
  const ordered = [...sources].sort((a, b) => Number(used.includes(b.id)) - Number(used.includes(a.id)));
  return (
    <ul className="sources">
      {ordered.map((s) => (
        <li key={s.id}>
          {used.includes(s.id) && <span className="tag">used here</span>}{" "}
          <a href={s.url} target="_blank" rel="noopener noreferrer">
            {s.citation}
          </a>
          {s.licence && <span className="muted"> · {s.licence}</span>}
        </li>
      ))}
    </ul>
  );
}

function Validation({ results }: { results: ValidationResult[] }) {
  if (!results.length) return <p>No validation results published for this model.</p>;
  const byDataset = new Map<string, ValidationResult[]>();
  for (const r of results) byDataset.set(r.dataset, [...(byDataset.get(r.dataset) ?? []), r]);
  return (
    <>
      {[...byDataset].map(([dataset, rows]) => (
        <Dropdown key={dataset} className="dataset" title={dataset} aside={<span className="muted">({rows[0]!.period})</span>}>
          <table className="table accuracy">
            <thead>
              <tr>
                <th scope="col">Measure</th>
                <th scope="col">Value</th>
                <th scope="col">Patients</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.metric}>
                  <th scope="row">{r.metric}</th>
                  <td>{r.value}</td>
                  <td>{r.n.toLocaleString("en")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Dropdown>
      ))}
    </>
  );
}
