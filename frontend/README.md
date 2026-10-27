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

## What's real vs. what's a demo aid

Every panel except "Simulate (dev only)" calls a real investigative
endpoint (`prepare` / `execute` / `recover`). The dev panel exists only
to demonstrate Level 2's staleness/recovery mechanism on demand
(tampering a file, revoking a mandate, making a hypothesis's
discriminating requirement unresolvable) — a real deployment would gate
or remove `krakadyl/api/app.py`'s `/api/dev/...` router entirely, not
ship it next to the real actions.

Use "Reset case" to replay the demo narrative from a clean state.
