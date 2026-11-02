/**
 * Localhost test harness for milestones 1–4: upload a file, pick a model, see the raw report.
 * Replaced by the designed site in milestone 5.
 */

import { useState } from "react";
import { formatRemaining } from "./engine/format";
import { MODELS } from "./engine/models";
import type { PrognosisReport } from "./engine/prognosis";
import { SOFT_LIMIT_BYTES } from "./parsing/upload";
import { runInWorker } from "./worker/client";

export function App() {
  const [file, setFile] = useState<File | null>(null);
  const [modelId, setModelId] = useState(MODELS[0]?.id ?? "");
  const [report, setReport] = useState<PrognosisReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!file) return;
    if (file.size > SOFT_LIMIT_BYTES && !window.confirm("This file is over 50 MB and may be slow to analyse. Continue?")) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await runInWorker(file, modelId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const spec = MODELS.find((m) => m.id === modelId);
  const headline = report && spec ? formatRemaining(report.result.median_years, spec.max_reliable_years) : null;

  return (
    <main>
      <h1>Death's Warrant — test harness</h1>
      <p>
        <input type="file" accept=".json,.xml" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </p>
      <p>
        <select value={modelId} onChange={(e) => setModelId(e.target.value)}>
          {MODELS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>{" "}
        <button type="button" disabled={!file || !modelId || busy} onClick={run}>
          {busy ? "Running…" : "Run Prognosis"}
        </button>
      </p>
      {error && <p role="alert">{error}</p>}
      {headline && (
        <h2>
          {headline.label}: {headline.value}
        </h2>
      )}
      {report && <pre>{JSON.stringify({ ...report, result: { ...report.result, curve: `${report.result.curve.length} points` } }, null, 2)}</pre>}
    </main>
  );
}
