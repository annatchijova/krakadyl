# Red Team — Level 3 Acquisition Authority (Live) — 2026-10-31

**Method:** Abductive Engineering (A–D–I) + `red-team-auditing`.
**Base:** `main` @ `33b8292`.
**Reproducible evidence:** `tools/redteam_acquisition_probes.py` — boots the real
uvicorn server capture-only (SAM disabled, so no Meta API call) and drives the
propose → authorize → capture path over HTTP.
**Outcome:** no new finding. The Level 3 acquisition authority invariants hold on
the real request path, including the dispatch-time mandate recheck the recent
remediation added.

## Scope

This round closes Level 3 by attacking the acquisition authority boundary as it
runs: who may authorize a capture, whether an authorization is single-use,
whether a capture mandate revoked between authorize and capture still lets the
capture through, and whether the image intake trusts the declared content type.
SAM is deliberately disabled (`KRAKADYL_ENABLE_SAM` unset), so every probe
exercises authorization and dispatch, not the processor, and spends nothing on
the Meta API. OS compromise is out of scope, except that A3 writes one row
directly to the SQLite file to simulate an out-of-band revocation — the same
persisted shape a legitimate revocation produces — in order to drive the
dispatch recheck.

## Threat model

- **Attacker CAN:** act as any configured operator; propose captures; replay a
  capture; submit arbitrary request bodies and Content-Type headers.
- **Attacker CANNOT:** forge the capture-mandate principal's token; break the
  single-use gate; break SHA-256.

## Epistemic legend

CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## Confirmed defenses (induction, live server)

| ID | Probe | Prediction | Observed | Level |
|----|-------|-----------|----------|-------|
| A1 | A non-principal operator (C) authorizes a capture | 403 | 403 | CONFIRMED BY INDUCTION |
| A1b | The capture-mandate principal (A) authorizes | 200 | 200 | CONFIRMED BY INDUCTION |
| A2 | Capture twice with one authorization (replay) | 1st 200, 2nd 409 | 1st 200, 2nd 409 | CONFIRMED BY INDUCTION |
| A3 | Capture mandate revoked after authorize, before capture | 409 refused | 409, "current mandate is revoked or differs from the approved revision" | CONFIRMED BY INDUCTION |
| A4 | Content-Type `image/png` but the bytes are JPEG | 415 | 415 | CONFIRMED BY INDUCTION |

**A1/A1b** confirm the capture authorization is bound to the capture mandate's
principal, not to any operator (`authorize_acquisition` rejects
`identity != capture_mandate.principal`, then re-validates the mandate id,
revision, and scope before and after issuing the grant).

**A2** confirms the one-shot authorization: the second capture is refused by the
gate's single-use workflow key, exactly as the execution nonce refuses a replayed
`PreparedAction`.

**A3** is the important one — it confirms the dispatch-time recheck the recent
remediation added is real and reads *current* state, not the authorization's
snapshot. `SQLiteAcquisitionGate.create_workflow` re-loads the capture mandate
from the store and refuses if its revision changed or `_mandate_is_current`
is false (revoked / outside its validity window). A grant issued while the
mandate was valid does not survive the mandate being revoked before the capture
is dispatched. The authorize-time check alone would not catch this; the dispatch
recheck does.

**A4** confirms the image intake is a decider≠actor boundary done right: the
endpoint accepts the capture only when the declared `Content-Type` and the bytes'
own magic number agree (`image_mime(content) == declared_type`), so a caller
cannot have the gate treat JPEG bytes as the PNG it declared. The type check runs
before dispatch, so it fires even on an otherwise-stale authorization.

## Discarded / confirmed-safe observations

| Vector | Result | Why |
|--------|--------|-----|
| Authorize someone else's proposal as a valid non-principal operator | Refused (A1) | principal binding in `authorize_acquisition` |
| Replay a single-use authorization | Refused (A2) | gate workflow is keyed one-shot per authorization |
| Spend a grant after its mandate was revoked | Refused (A3) | `create_workflow`/`begin_phase` re-read the current mandate and check revision + `_mandate_is_current` |
| Smuggle non-PNG bytes under a PNG Content-Type | Refused (A4) | `image_mime(content)` must equal the declared type |
| A rejected capture (415) burning the authorization | Does not happen | the type check precedes dispatch; the grant is untouched |

## Result

No new finding. Level 3's acquisition authority — principal-bound authorization,
single-use grants, dispatch-time revalidation of the current capture mandate, and
a content-type/bytes-agreement intake check — holds on the real HTTP path. With
RT-API-01 (read authorization) and RT-CHAIN-01/02 (receipt chain) fixed in
earlier rounds today, and Levels 4 and 3 confirmed by induction, the live
authority surface has been exercised end to end. Recorded for the adversarial
trail: a confirmed defense, earned by attempting the bypasses, not asserted.
