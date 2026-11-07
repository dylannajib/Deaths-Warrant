/** The page: links, title, coverage, upload, disease group, run, result, disclaimer, release notes. */

import { useEffect, useRef, useState } from "react";
import founderPfp from "./assets/founder-pfp.png";
import githubLogo from "./assets/github-logo.webp";
import type { Observed } from "./engine/evaluate";
import { MODELS } from "./engine/models";
import type { PrognosisReport } from "./engine/prognosis";
import type { Input } from "./engine/spec";
import { githubProfile, REPO_URL } from "./links";
import { SOFT_LIMIT_BYTES } from "./parsing/upload";
import { AskInput } from "./ui/AskInput";
import { Dropdown } from "./ui/Dropdown";
import { ReleaseNotes } from "./ui/ReleaseNotes";
import { ResultView } from "./ui/ResultView";
import { RunError, runInWorker } from "./worker/client";

const FOUNDER = "dylannajib";

/** A failed run: the message, and the required input to ask the user for when that is what failed. */
interface Failure {
  message: string;
  missing: Input | null;
}

const sizeLabel = (bytes: number) =>
  bytes >= 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1e3))} KB`;

export function App() {
  const [file, setFile] = useState<File | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [report, setReport] = useState<PrognosisReport | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [busy, setBusy] = useState(false);
  // Values the user typed in for required inputs the record lacks.
  const [entered, setEntered] = useState<Observed>({});
  const upload = useRef<HTMLInputElement>(null);

  // runId is bumped whenever the outcome is dropped, so a run still in flight cannot bring it back.
  const runId = useRef(0);
  const resetOutcome = () => {
    runId.current += 1;
    setReport(null);
    setFailure(null);
  };

  // The file is only read during a run. The page lets go of it, and of the result (which shows
  // details from the record), when the user clears the result or leaves the page.
  const clearAll = () => {
    resetOutcome();
    setFile(null);
    setModelId(null);
    setEntered({});
    if (upload.current) upload.current.value = "";
  };
  useEffect(() => {
    window.addEventListener("pagehide", clearAll);
    return () => window.removeEventListener("pagehide", clearAll);
  }, []);

  const run = async (values: Observed = entered) => {
    if (!file || !modelId) return;
    resetOutcome();
    setBusy(true);
    const id = runId.current;
    try {
      const result = await runInWorker(file, modelId, values);
      if (id === runId.current) setReport(result);
    } catch (e) {
      if (id === runId.current) {
        setFailure({ message: e instanceof Error ? e.message : String(e), missing: e instanceof RunError ? e.missing : null });
      }
    } finally {
      setBusy(false);
    }
  };

  // Clicking the checked group again unchecks it (a radio's change event never fires for that).
  const choose = (id: string | null) => {
    setModelId(id);
    resetOutcome();
  };

  const missing = failure?.missing;
  return (
    <>
      <nav className="links" aria-label="Project links">
        <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
          <img src={githubLogo} alt="" width={24} height={24} />
          GitHub Repository
        </a>
        <h2>Contributors</h2>
        <a className="person" href={githubProfile(FOUNDER)} target="_blank" rel="noopener noreferrer">
          <img src={founderPfp} alt="" width={24} height={24} />
          <span>
            <strong>Founder</strong> @{FOUNDER}
          </span>
        </a>
      </nav>

      <div className="paper">
        <main className="page">
          <header className="hero">
            <h1>Death’s Warrant</h1>
            <p className="tagline">a free, open-source, prognostic life expectancy estimator</p>
          </header>

          <section className="coverage" aria-labelledby="coverage-title">
            <h2 id="coverage-title">Currently Covering</h2>
            <p>{MODELS.map((m) => m.name).join(", ")}</p>
          </section>

          <section className="form">
            <div className="upload">
              <label className="field">
                <strong>Upload Your Patient Data</strong>
                <input
                  ref={upload}
                  className="visually-hidden"
                  type="file"
                  aria-describedby="upload-hint"
                  disabled={busy}
                  accept=".json,.xml,application/json,application/xml,text/xml"
                  onChange={(e) => {
                    setFile(e.target.files?.[0] ?? null);
                    setEntered({});
                    resetOutcome();
                  }}
                />
              </label>
              <span id="upload-hint" className="hint">
                {file ? `${file.name} (${sizeLabel(file.size)})` : "FHIR.json, FHIR.xml or C‑CDA.xml"}
              </span>
            </div>
            {file && file.size > SOFT_LIMIT_BYTES && (
              <p className="hint warn">This file is over {SOFT_LIMIT_BYTES / 1024 / 1024} MB, so it may take a while to analyse.</p>
            )}

            <Dropdown className="picker field" title={<strong>Select Your Disease Group</strong>}>
              <fieldset>
                <legend className="visually-hidden">Disease group</legend>
                {MODELS.map((m) => (
                  <label key={m.id} className="option">
                    <input
                      type="radio"
                      name="disease-group"
                      value={m.id}
                      checked={m.id === modelId}
                      onChange={() => choose(m.id)}
                      onClick={() => m.id === modelId && choose(null)}
                    />
                    {m.name}
                  </label>
                ))}
              </fieldset>
            </Dropdown>
          </section>

          <div className="run">
            <button type="button" onClick={() => run()} disabled={!file || !modelId || busy}>
              {busy ? "Running…" : "Run Prognosis"}
            </button>
          </div>

          <div aria-live="polite">
            {failure && (
              <div className="error" role="alert">
                <p>{failure.message}</p>
                {missing && (
                  <AskInput
                    key={missing.id}
                    input={missing}
                    onSubmit={(value) => {
                      const values = { ...entered, [missing.id]: value };
                      setEntered(values);
                      void run(values);
                    }}
                  />
                )}
              </div>
            )}
            {report && (
              <>
                <ResultView report={report} />
                <button type="button" className="clear" onClick={clearAll}>
                  Clear
                </button>
              </>
            )}
          </div>
        </main>

        <footer className="disclaimer">
          <p>Death’s Warrant is not a clinically-validated tool. Treat your results as an estimate subject to change.</p>
          <p>Any data you upload is read, analysed and then discarded locally in your browser.</p>
        </footer>
      </div>

      <ReleaseNotes />
    </>
  );
}
