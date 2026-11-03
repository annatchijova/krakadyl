[English](getting-started.md) · [Español](getting-started.es.md)

# Run KRAKADYL on your machine

A reproduction guide for judges and reviewers: clone the repo, start the
backend and the workspace, and drive the same four cases shown in the demo
video. Every button calls a real endpoint and the exact `krakadyl.core`
functions the tests exercise — nothing on the page is a mock. With your own
Meta key, Muse Spark and SAM 3.1 run live.

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer (for the Vite frontend)
- git
- A Meta API key with hackathon credits — this is a Meta hackathon, so plug in
  your own key and watch Muse Spark and SAM 3.1 work. Without it the
  deterministic core still runs fully; only "Ask Muse" and SAM captures refuse,
  honestly and before any call.

## 1. Get the code

```
git clone https://github.com/annatchijova/krakadyl.git
cd krakadyl
```

## 2. Install the backend

A virtualenv is recommended so the install stays isolated:

```
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e '.[api]'
```

Optional: `pip install -e '.[api,laya]'` also enables the "Handoff note (Laya)"
panel. Without the `laya` extra, that one panel returns a clear 503 and nothing
else is affected.

## 3. Generate operator tokens

```
python tools/operator_token.py investigator-A investigator-C
```

This prints each token once (you log in with these — they are never stored) and
an `export KRAKADYL_OPERATOR_TOKENS='...'` line that holds only SHA-256 hashes.
Keep the two tokens somewhere for the login screen.

- `investigator-A` acts: prepare, execute, propose and dispatch captures.
- `investigator-C` evaluates independently — the second pair of eyes that
  resolves an acquisition requirement. A self-evaluation is recorded as a claim,
  never as a resolution.

## 4. Start the backend

In the shell that will run the backend, set the credentials and your Meta key,
then start the server:

```
export KRAKADYL_OPERATOR_TOKENS='investigator-A=...;investigator-C=...'   # from step 3
export META_API_KEY='your-meta-key'                                       # your own Meta key

KRAKADYL_ENABLE_SAM=1 KRAKADYL_ENABLE_DEV_ROUTES=1 \
  uvicorn krakadyl.api.app:app --port 8000
```

- The four demo cases seed automatically on first boot.
- `KRAKADYL_ENABLE_SAM=1` turns on live SAM 3.1 captures.
- `KRAKADYL_ENABLE_DEV_ROUTES=1` turns on the Simulate panel so you can trigger
  staleness (tamper a file, revoke a mandate). A real deployment gates this.

The backend is ready when `http://localhost:8000/openapi.json` responds.

## 5. Start the workspace

In a second terminal:

```
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` and log in with the `investigator-A` token. The
frontend targets `http://localhost:8000` by default; if you ran the backend on a
different port, start it with `VITE_API_BASE=http://localhost:PORT npm run dev`.

## 6. What you will see — the four cases

The case selector at the top switches between the four seeded cases:

| Case | What it demonstrates | Verdict |
|---|---|---|
| `case-001` | Verified and in scope — the export is cleared and sealed | `ALLOWED` |
| `case-gather` | A requirement is still open but an authorized source can resolve it | `GATHER_EVIDENCE` |
| `case-lost` | Reported done, never independently verified, no longer recoverable | `FORBIDDEN` |
| `case-scope` | The action falls outside the mandate's scope | `FORBIDDEN` |

Things to try:

- **Prepare, then Execute.** Prepare decides (free, deterministic); Execute
  revalidates everything and seals a chained receipt. The two are separate on
  purpose: time passes between deciding and acting.
- **Ask Muse.** A real, billed Meta call proposes the next action — and the
  deterministic engine still checks it exactly like a hand-built action. The
  proposal is display-only until the engine rules on it.
- **Acquisition.** Propose and dispatch a capture as `investigator-A`, then
  evaluate it as `investigator-C`. Only the independent evaluator resolves the
  requirement.
- **Simulate (dev panel).** Tamper a file or revoke the mandate, then Execute
  again: the same prepared action is now refused, and the refusal is sealed in a
  receipt. "Refused, here is exactly why" is a first-class outcome.

## Billing and offline behavior

"Ask Muse" and SAM captures are real, billed Meta calls. Without `META_API_KEY`
they refuse before any call, with a clear reason — while reads, Prepare,
Execute, staleness, recovery, and delegation need no network at all. That is the
honest-degradation property, demonstrated rather than described.

## Going deeper

- Reproduce cases headlessly: `demo/run_case_001.py` and the other
  `demo/run_case_*.py` scripts; `tools/api_smoke.py` walks the core narrative.
- Frontend development detail (API type generation, ports): `frontend/README.md`.
- Architecture and guarantees: `TECHNICAL_README.md`.
- What is honestly not claimed: `docs/known-limitations.md`.
- The hosted judge demo (Docker + public HTTPS): `docs/judge-demo-guide.md`.
