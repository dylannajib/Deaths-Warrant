/** The headline, warnings, and the "See more" and "Reasoning" dropdowns for one report. */

import type { PrognosisReport } from "../engine/prognosis";
import type { Source, ValidationResult } from "../engine/spec";
import { formatAssumed, formatDuration, formatPercent, formatRemaining, formatValue } from "./format";
import { Dropdown } from "./Dropdown";
import { SurvivalChart } from "./SurvivalChart";

const FORMAT_LABEL = { "fhir-json": "FHIR JSON", "fhir-xml": "FHIR XML", ccda: "C-CDA" } as const;

export function ResultView({ report }: { report: PrognosisReport }) {
  const { result, model } = report;
  const headline = formatRemaining(result.median_years, model.max_reliable_years);
  return (
    <section className="result" aria-label="Your result">
      <p className="headline">
        {headline.label}: <strong>{headline.value}</strong>
      </p>
      <p className="basis">
        {model.name} model · {model.layer.label}
      </p>
      {report.warnings.length > 0 && (
        <ul className="warnings">
          {report.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <Dropdown className="drop" title="See more">
        <SeeMore report={report} />
      </Dropdown>
      <Dropdown className="drop" title="Reasoning">
        <Reasoning report={report} />
      </Dropdown>
    </section>
  );
}

function SeeMore({ report }: { report: PrognosisReport }) {
  const r = report.result;
  return (
    <div className="drop-body">
      <p>
        Half of people in your situation are estimated to live longer than {formatDuration(r.median_years)}, and half
        less. The middle half are estimated to live between {formatDuration(r.range_low_years)} and{" "}
        {formatDuration(r.range_high_years)}.
      </p>
      <SurvivalChart curve={r.curve} medianYears={r.median_years} />
      <table className="table">
        <caption>Estimated chance of being alive</caption>
        <thead>
          <tr>
            {Object.keys(r.survival_at).map((t) => (
              <th key={t} scope="col">
                In {t} year{t === "1" ? "" : "s"}
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
        <strong>{model.layer.label}</strong> ({model.name} model, version {model.version}). {model.layer.description}
      </p>
      {result.skipped_layers.length > 0 && (
        <ul>
          {result.skipped_layers.map((l) => (
            <li key={l.id}>
              More specific option not used, <em>{l.label}</em>: needs {l.lacking.map(label).join(", ")}.
            </li>
          ))}
        </ul>
      )}
      {result.beyond_reliable && (
        <p>
          The model's computed median is {formatDuration(result.median_years)}. Beyond {model.max_reliable_years} years
          the estimate rests on extrapolating published survival, so it is shown as "{model.max_reliable_years}+".
        </p>
      )}

      <h3>What was read from your record</h3>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Input</th>
            <th scope="col">Value</th>
            <th scope="col">Where it came from</th>
          </tr>
        </thead>
        <tbody>
          {used.map((i) => {
            const unit = model.inputs[i.id]?.unit ?? null;
            const where =
              i.status === "implausible"
                ? `${provenance[i.id]}; outside the plausible range, so ignored`
                : provenance[i.id];
            return (
              <tr key={i.id}>
                <th scope="row">{label(i.id)}</th>
                <td>{i.assumed ? `Averaged: ${formatAssumed(i.assumed, unit)}` : formatValue(i.value, unit)}</td>
                <td>{i.assumed && i.status === "missing" ? `${where}; averaged over the published population` : where}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <Terms report={report} label={label} />

      <h3>Assumptions</h3>
      <ul>
        <li>
          Estimated as of {report.asOf}, from a {FORMAT_LABEL[report.format]} file, using U.S. population mortality for
          your age and sex.
        </li>
        <li>Inputs missing from your record are averaged over published population data, which widens the range.</li>
        {report.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>

      <h3>Sources</h3>
      <SourceList sources={model.sources} used={model.layer.sources} />

      <h3>How accurate has this model been?</h3>
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
      <table className="table">
        <tbody>
          {terms.map((t, k) => (
            <tr key={`${t.input}-${k}`}>
              <th scope="row">{label(t.input)}</th>
              <td>
                {t.contribution === null
                  ? "averaged (not recorded)"
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
          {used.includes(s.id) && <span className="tag">used here</span>} {s.citation}{" "}
          <a href={s.url} target="_blank" rel="noopener noreferrer">
            Link
          </a>
          {s.licence && <span className="muted"> · {s.licence}</span>}
        </li>
      ))}
    </ul>
  );
}

function Validation({ results }: { results: ValidationResult[] }) {
  if (!results.length) return <p>No validation results have been published for this model yet.</p>;
  const byDataset = new Map<string, ValidationResult[]>();
  for (const r of results) byDataset.set(r.dataset, [...(byDataset.get(r.dataset) ?? []), r]);
  return (
    <>
      <p>
        Tested only on real, published patient data, never data the model was built from. Each figure compares the
        model's prediction with what actually happened.
      </p>
      {[...byDataset].map(([dataset, rows]) => (
        <details key={dataset} className="dataset">
          <summary>
            {dataset} <span className="muted">({rows[0]!.period})</span>
          </summary>
          <p className="muted">{rows[0]!.notes}</p>
          <table className="table">
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
        </details>
      ))}
    </>
  );
}

