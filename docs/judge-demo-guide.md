# Judge Demo Guide

What a hackathon judge gets: a live investigator workspace in the browser,
talking to a real backend over HTTPS. Every button calls a real endpoint;
every decision shown was made by the deterministic core, sealed, and
receipted. Nothing on the page is a mock.

## The 3-minute path

Log in with the operator token provided (paste it on the auth screen — it
stays in tab memory only, never persisted). The seeded case `case-001` is a
two-device synthetic case: `device-A` is in mandate scope, `device-B` is not.

1. **Mission + Evidence.** Read the case state: what is verified, what is
   missing, what sits outside the mandate. Note `device-B` flagged
   out-of-scope — the system says so instead of silently including it.
2. **Prepare, then Execute.** Press "Prepare" (free, deterministic), read the
   decision, then "Execute". A chained receipt appears with its seal.
   Prepare and Execute are separate on purpose: time passes between deciding
   and acting, and Execute revalidates everything before touching anything.
3. **Ask Muse (1 billed call).** Press "Ask Muse": a real call to Meta Muse
   Spark proposes the next action, and the deterministic engine still checks
   it exactly like a hand-built action. The proposal is display-only until
   the engine rules on it.
4. **Staleness on demand (Simulate panel, dev only).** Tamper a file or
   revoke the mandate, then Execute again: the same prepared action is now
   refused, with the reason sealed in a receipt. Refusals are permanent
   records here, not silent failures.
5. **Acquisition (Level 3 panel).** Propose a bounded capture as
   `investigator-A`, dispatch it, then evaluate it as `investigator-C`:
   only an independent evaluator resolves the requirement. A
   self-evaluation is recorded as a claim, never as a resolution.

If only one property survives the demo, let it be this: **the model
proposes, the environment verifies, the deterministic engine decides —
and "refused, here is exactly why" is a first-class, sealed outcome.**

## What is live, billed, or degraded

| Path | State in the demo |
|---|---|
| Prepare / Execute / Recover, all reads | Live, free, deterministic |
| Ask Muse | Live, one billed Meta API call per click (hackathon credits) |
| SAM 3.1 capture segmentation | Live, billed per capture, only when enabled |
| Analyze with Laya | Honest `503` in this deployment (the `torch` extra is not installed in the demo image); the core is unaffected |
| Simulate (dev only) | Enabled for the demo so judges can trigger staleness; a real deployment gates it |

## Credentials

Judges receive two operator tokens (delivered out of band, never committed):

- `investigator-A` — acts: prepare, execute, propose and dispatch captures.
- `investigator-C` — evaluates independently: the second pair of eyes that
  resolves acquisition requirements.

The Bearer [REDACTED] not a request-body name, determines authority: the
same token pasted into the login screen is what the backend checks on every
call. Tokens are random 256-bit strings; the server stores only SHA-256
hashes (`KRAKADYL_OPERATOR_TOKENS`).

## Deploy recipe (what the demo runs on)

Backend (Docker, any host that runs a container — Render, Railway, Fly.io,
a VPS):

```
docker build -t krakadyl-api .
docker run -p 8000:8000 \
  -e KRAKADYL_OPERATOR_TOKENS='<hashes from tools/operator_token.py>' \
  -e META_API_KEY='<Meta key with hackathon credits>' \
  -e KRAKADYL_ENABLE_SAM=1 \
  -e KRAKADYL_ENABLE_DEV_ROUTES=1 \
  -e KRAKADYL_CORS_ORIGINS='https://<vercel-app>.vercel.app' \
  krakadyl-api
```

Frontend (Vercel, from `frontend/`):

```
VITE_API_BASE=https://<backend-host> npm run build
```

Set `VITE_API_BASE` as a Vercel environment variable and deploy. Order
matters: deploy the frontend first to learn its `*.vercel.app` URL, then
set `KRAKADYL_CORS_ORIGINS` on the backend to exactly that origin
(a `*` origin is refused at startup — the API names its callers).

Verify before handing the URL to judges: log in with the A token, run the
3-minute path above, then log in with the C token and resolve one capture.
`tools/api_smoke.py` covers the same core narrative headlessly.

## Offline fallback

If the venue network or the Meta API is unreachable, the deterministic
core still demonstrates fully: reads, Prepare, Execute, staleness,
recovery, delegation, and resume need no network at all. Only "Ask Muse"
and SAM captures refuse (before any call, with a clear reason) — which is
itself the honest-degradation property, demonstrated live rather than
described.

## Reset and expiry

- A backend restart reseeds the demo case to a clean state (by design on
  ephemeral disks — judges always start from the same case).
- Seeded mandates are valid 30 days from 2026-10-27 (through judging,
  ~2026-11-26). Past expiry the system is correctly `FORBIDDEN` everywhere
  until re-seeded — correct behavior, not a bug.

## Where the depth lives

- Architecture and guarantees: `TECHNICAL_README.md`.
- What is honestly not claimed: `docs/known-limitations.md` (KL-001..KL-005).
- Acceptance gates for this demo: `docs/presentation-delivery-plan.md`.
