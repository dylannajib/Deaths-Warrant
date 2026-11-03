/** The page: links, title, coverage, upload, disease group, run, result, disclaimer. */

import { useRef, useState } from "react";
import founderPfp from "../assets/founder-pfp.png";
import githubLogo from "../assets/github-logo.png";
import { MODELS } from "./engine/models";
import type { PrognosisReport } from "./engine/prognosis";
import { SOFT_LIMIT_BYTES } from "./parsing/upload";
import { ResultView } from "./ui/ResultView";
import { runInWorker } from "./worker/client";

const REPO_URL = "https://github.com/dylannajib/Deaths-Warrant";
const FOUNDER_URL = "https://github.com/dylannajib";

const sizeLabel = (bytes: number) =>
  bytes >= 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1e3))} KB`;

export function App() {
  const [file, setFile] = useState<File | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [report, setReport] = useState<PrognosisReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const picker = useRef<HTMLDetailsElement>(null);
  const model = MODELS.find((m) => m.id === modelId);

  const run = async () => {
    if (!file || !modelId) return;
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

  const choose = (id: string) => {
    setModelId(id);
    setReport(null);
    if (picker.current) picker.current.open = false;
  };

  return (
    <>
      <nav className="links" aria-label="Project links">
        <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
          <img className="mark" src={githubLogo} alt="" width={20} height={20} />
          GitHub Repository
        </a>
        <a href={FOUNDER_URL} target="_blank" rel="noopener noreferrer">
          <img className="round" src={founderPfp} alt="" width={20} height={20} />
          Founder’s GitHub
        </a>
      </nav>

      <main className="page">
        <header className="hero">
          <h1>Death’s Warrant</h1>
          <p className="tagline">a free, open-source prognosis service</p>
          <p className="lede">Know how long you likely have left.</p>
        </header>

        <section className="coverage" aria-labelledby="coverage-title">
          <h2 id="coverage-title">Current Coverage</h2>
          <p>{MODELS.map((m) => m.name).join(" - ")}</p>
        </section>

        <section className="form">
          <label className="upload">
            <span className="field">
              <strong>Upload:</strong> FHIR.json, FHIR.xml or C‑CDA.xml
            </span>
            <input
              className="visually-hidden"
              type="file"
              accept=".json,.xml,application/json,application/xml,text/xml"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setReport(null);
                setError(null);
              }}
            />
            <span className="hint">
              {file ? `Selected: ${file.name} (${sizeLabel(file.size)})` : "Request your patient data as one of these formats from your hospital"}
            </span>
          </label>
          {file && file.size > SOFT_LIMIT_BYTES && (
            <p className="hint warn">This file is over 50 MB, so it may take a while to analyse.</p>
          )}

          <details className="picker" ref={picker}>
            <summary className="field">
              <span aria-hidden="true">&gt; </span>
              {model ? (
                <>
                  <strong>Disease Group:</strong> {model.name}
                </>
              ) : (
                <strong>Pick your Disease Group</strong>
              )}
            </summary>
            <fieldset>
              <legend className="visually-hidden">Disease group</legend>
              {MODELS.map((m) => (
                <label key={m.id} className="option">
                  <input type="radio" name="disease-group" value={m.id} checked={m.id === modelId} onChange={() => choose(m.id)} />
                  <span>
                    <strong>{m.name}</strong>
                    <span className="hint">{m.description}</span>
                  </span>
                </label>
              ))}
            </fieldset>
          </details>
        </section>

        <div className="run">
          <button type="button" onClick={run} disabled={!file || !modelId || busy} aria-describedby="run-hint">
            {busy ? "Running…" : "Run Prognosis"}
          </button>
          <p id="run-hint" className="hint">
            {!file || !modelId ? "Choose a file and a disease group first." : "Your file stays on this device."}
          </p>
        </div>

        <div aria-live="polite">
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {report && <ResultView report={report} />}
        </div>
      </main>

      <footer className="disclaimer">
        <p>Death’s Warrant is not a clinically-validated tool. Treat your results as an estimate subject to change.</p>
        <p>Your file never leaves your device: it is read and analysed in your browser, then discarded.</p>
      </footer>
    </>
  );
}
