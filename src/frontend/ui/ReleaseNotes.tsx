/** What changed in each release, newest first. Add a release by adding an entry at the top. */

const RELEASES = [
  {
    version: "0.1.0",
    date: "November 2026",
    notes: [
      "First release.",
      "Estimates for cancer, cardiovascular disease and chronic lower respiratory diseases.",
      "Reads FHIR JSON, FHIR XML and C-CDA records entirely in your browser.",
    ],
  },
];

export function ReleaseNotes() {
  return (
    <aside className="release-notes" aria-labelledby="release-notes-title">
      <h2 id="release-notes-title">Release Notes</h2>
      {RELEASES.map((r) => (
        <section key={r.version}>
          <h3>
            Version {r.version} <span className="muted">({r.date})</span>
          </h3>
          <ul>
            {r.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}
