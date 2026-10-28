# KRAKADYL — Case Workspace

React + TypeScript frontend over `krakadyl/api` (FastAPI). No mocked
state: every button here calls a real endpoint, which calls the exact
same `krakadyl.core` functions the test suite and demo scripts exercise
— see `docs/language-decision.md` for why the split is Python core /
TypeScript frontend.

## Run it

Backend (from the repo root, with the `api` extra installed —
`pip install -e '.[api]'`):

```
KRAKADYL_DATA_DIR=out/api uvicorn krakadyl.api.app:app --port 8000
```

The "Ask Muse" and "Handoff note (Laya)" panels need their own extras
(`pip install -e '.[api,laya]'`) plus `META_API_KEY` in `.env` for
Muse. Without the `laya` extra installed, "Analyze with Laya" returns
a clear 503 rather than breaking anything else — see
`docs/red-team-laya-integration.md` for why `laya` is pinned to an
exact reviewed version, not a range. Laya runs locally (no billing,
but the first real call downloads a model checkpoint from
HuggingFace); Muse makes a real, billed call to the Meta Model API
every time "Ask Muse" is clicked — a separate button from the free
"Prepare" on purpose, same reasoning as `docs/levels.md`'s Muse
section.

Running the API without any venv isolation is fine if you only need
`prepare`/`execute`/`recover`/`propose-with-muse`. The `laya` extra
pulls in `torch`/`transformers`, which is worth isolating in its own
virtualenv if this machine runs other Python projects with their own
pinned versions of those — exactly the reasoning documented in
`docs/levels.md`'s Laya section.

If port 8000 is already taken on your machine by something else,
start uvicorn on another port and point the frontend at it:

```
VITE_API_BASE=http://localhost:8010 npm run dev
```

Frontend (from `frontend/`):

```
npm install
npm run dev
```

Opens on `http://localhost:5173`. The case (`case-001`, the same
two-device synthetic case as `demo/run_case_001.py` and
`demo/run_case_002_level2.py`) is seeded into `out/api/krakadyl.db` on
first backend startup, and persists across restarts and page reloads.

## Regenerate API types

The FastAPI backend must be serving this checkout's `/openapi.json` on
port 8000. From `frontend/`:

```
npm ci --prefix tools/openapi-codegen --ignore-scripts
npm run gen:api-types
npx tsc -b
```

Run this whenever a Pydantic request or response model in
`krakadyl/api/app.py` changes. Commit the regenerated
`src/api-generated.ts`; do not edit it by hand. The generator has its
own exact-version lockfile because `openapi-typescript@7.13.0` requires
TypeScript 5 while the application intentionally compiles with
TypeScript 7. Keeping those toolchains separate avoids weakening either
dependency contract.

Most UI-facing types are direct aliases of generated Pydantic schemas.
Activity events and execution manifests remain narrowly refined in
`src/api.ts` because those two Python responses currently expose generic
dictionaries in OpenAPI; see `docs/language-decision.md` for the exact
limit.

## What's real vs. what's a demo aid

Every panel except "Simulate (dev only)" calls a real investigative
endpoint (`prepare` / `execute` / `recover`). The dev panel exists only
to demonstrate Level 2's staleness/recovery mechanism on demand
(tampering a file, revoking a mandate, making a hypothesis's
discriminating requirement unresolvable) — a real deployment would gate
or remove `krakadyl/api/app.py`'s `/api/dev/...` router entirely, not
ship it next to the real actions.

Use "Reset case" to replay the demo narrative from a clean state.
