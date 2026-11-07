/** What changed in each release, newest first. Add a release by adding an entry at the top. */

import { Dropdown } from "./Dropdown";

const RELEASES = [
  {
    version: "0.1.0",
    date: "4 Nov 2026",
    author: "dylannajib",
    notes: ["Hello, World!", "+ Models: Cancer, Cardiovascular, Chronic Lower Respiratory", "+ Formats: FHIR.json, FHIR.xml, C-CDA.xml"],
  },
];

export function ReleaseNotes() {
  return (
    <aside className="release-notes" aria-labelledby="release-notes-title">
      <h2 id="release-notes-title">Release Notes</h2>
      {RELEASES.map((r) => (
        <Dropdown
          key={r.version}
          className="release"
          title={`v${r.version} - ${r.date}`}
          after={
            <a href={`https://github.com/${r.author}`} target="_blank" rel="noopener noreferrer">
              (@{r.author})
            </a>
          }
        >
          <ul>
            {r.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Dropdown>
      ))}
    </aside>
  );
}
