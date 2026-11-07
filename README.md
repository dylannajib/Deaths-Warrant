# Death's Warrant

A free, open-source, prognostic life expectancy estimator. Upload your patient record (FHIR JSON, FHIR XML or C-CDA), pick your disease group, and get an estimate of how many years you likely have left with the reasoning behind it.

## Privacy

Death's Warrant runs in your browser, in a Web Worker that is thrown away after each run. It hosts no server, database, analytics or third-party script,
and the Content Security Policy (`connect-src 'self'`, set in `src/frontend/vite.config.ts`) stops your browser from sending data anywhere else.

## Layout

```
src/
  prognosis-models/<group>/   one folder per disease group (see CONTRIBUTING.md)
  prognosis-models/_shared/   population life tables
  backend/general/            offline Python pipeline: spec schema, evaluator, export
  backend/tests/
  frontend/                   React + TypeScript site: parses uploads, runs spec.json
```

Each model is layered. A base layer (population mortality × published hazard ratios) covers
any condition in the group. More specific layers (cancer site × stage, MAGGIC for heart
failure, ADO for COPD) take over when the record has their inputs. Missing inputs are
averaged over published population data, which widens the range.

Python is the reference evaluator and the browser runs a TypeScript port. CI checks they agree
on every case in each model's `golden.json`.

## Models

| Group | Method | Accuracy (see [TESTING.md](TESTING.md)) |
|---|---|---|
| Cancer | U.S. life tables × SEER relative survival by site, stage and age | C-index 0.71 on 24,067 MSK-CHORD patients |
| Cardiovascular | MAGGIC, heart failure and stroke survival by age, or hazard ratios | C-index 0.74 on 1,084 FAR NHL patients |
| Chronic lower respiratory | ADO index, or hazard ratios for COPD, bronchiectasis, asthma | C-index 0.78 on 2,602 NHANES patients |

Each model's `sources.md` has its method, sources and results.

## Development

Python 3.14 and Node 22.

```bash
python3 -m venv .venv && .venv/bin/pip install -r src/backend/requirements-dev.txt
```

```bash
cd src/backend && ../../.venv/bin/python -m pytest && ../../.venv/bin/python -m general.export
```

```bash
cd src/frontend && npm ci && npm test && npm run dev
```

## Dependencies

| Package | Why |
|---|---|
| react, react-dom | UI (project requirement) |
| typescript, vite, @vitejs/plugin-react, vitest | type checking, build, tests |
| @types/react, @types/react-dom, @types/node | type definitions (node only for tests) |
| pydantic | validates every model spec (project requirement) |
| pytest, ruff | Python tests and lint |
| Cormorant Garamond, Beth Ellen | self-hosted fonts (SIL OFL 1.1, `src/frontend/public/fonts/`) |

The XML parser is our own (about 200 lines). `DOMParser` is not available in Web Workers, and
our parser refuses any DOCTYPE or ENTITY, which rules out XXE and entity-expansion attacks.
