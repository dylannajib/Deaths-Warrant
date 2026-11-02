# Death's Warrant

A free, open-source prognosis service. Upload your patient record (FHIR JSON, FHIR XML or
C-CDA XML), pick your disease group, and get an estimate of how many years you likely have
left, with the full reasoning behind it.

> Death's Warrant is not a clinically validated tool. Treat results as an estimate subject to
> change, and discuss them with your care team.

## Privacy by architecture

Your file **never leaves your device**. Parsing and prognosis run entirely in your browser,
in a Web Worker that is discarded after each run. There is no server-side code, no database,
no analytics and no third-party scripts. The production Content Security Policy sets
`connect-src 'self'`, so the browser itself refuses to send data to any other site. Because
the code is open source, you can check this claim yourself (and watch the Network tab).

## How it works

```
src/
  models/<group>/        one folder per disease group
    model.py             model definition, built only from published, citable sources
    spec.json            exported coefficients (generated)
    golden.json          reference test cases (generated)
    sources.md           citations and licences
  backend/               offline Python pipeline: spec schema, reference evaluator,
                         export, accuracy validation (never runs on the website)
  frontend/              React + TypeScript site; parses uploads and runs spec.json
```

* **Models** are broad, one per disease group, and layered. A *base layer* (population life
  table × diagnosis-specific hazard ratio × comorbidity) covers every condition in the group.
  *Refinement layers* (e.g. cancer site × stage survival, MAGGIC for heart failure, ADO/BODE
  for COPD) take over when the record has the inputs they need. Missing inputs are averaged
  over published population distributions, which widens the reported range.
* **Two implementations, one answer.** Python is the reference; the browser runs a
  TypeScript port. CI replays every `golden.json` against the TypeScript evaluator.
* **Accuracy** is tested only against real, published patient data, never data we invent.
  Patient-level datasets are used solely for testing, never for training, and are never
  committed (see `.gitignore`); only aggregate results are published.

## Development

Requirements: Python 3.14, Node 22.

```bash
python3 -m venv .venv && .venv/bin/pip install -r src/backend/requirements-dev.txt
```

```bash
cd src/backend && ../../.venv/bin/python -m pytest && ../../.venv/bin/python -m deaths_warrant.export
```

```bash
cd src/frontend && npm ci && npm test && npm run dev
```

`npm run dev` serves the localhost site; dev mode also lists the unit-test fixture model.

## Adding a disease group

See [CONTRIBUTING.md](CONTRIBUTING.md). A new model is a new folder under `src/models/`; no
frontend changes are needed.

## Dependencies

| Package | Where | Why |
|---|---|---|
| react, react-dom | site | UI framework (project requirement) |
| typescript | dev | type checking (project requirement) |
| vite, @vitejs/plugin-react | dev | build and dev server; the official React plugin is the only plugin |
| vitest | dev | tests, including golden parity |
| @types/react, @types/react-dom, @types/node | dev | type definitions |
| pydantic | pipeline | validates every model spec (project requirement) |
| pytest, ruff | pipeline dev | tests and lint |

The XML parser is our own (~200 lines): the browser's `DOMParser` is not available in Web
Workers, and owning the parser lets us reject DOCTYPE/ENTITY declarations outright, which
rules out XXE and entity-expansion attacks.
