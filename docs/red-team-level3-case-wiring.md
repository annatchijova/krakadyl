# Red team — Level 3 case wiring (2026-10-30)

Scope: the four commits on `feat/level3-case-acquisition` that wired acquisition into the case (`acquisition_routes.py`, `evaluation.py`, `acquisition_runtime.py`, the Level 3 API section, `AcquisitionPanel.tsx`). Method: adversarial re-read of every new path that can capture, spend, resolve, close, or reveal; each candidate was reproduced as a failing test before any fix (`tests/test_red_team_level3.py`, 8 failing → 0 after fixes). The pre-existing gate and coordinator were not re-audited here; they have their own red-team records.

## Findings fixed

| # | Severity | Finding (reproduced) | Fix |
|---|---|---|---|
| F1 | High | A capture approved for question Q1 could be evaluated as `SUPPORTS` after the requirement was reworded to Q2, resolving Q2 with evidence never gathered for it. The revision check only compared the *current* requirement with what the evaluator saw, not with what the capture was approved for. | `record_evaluation` refuses when the requirement's question or answer classes differ from the workflow's approved need snapshot. |
| F2 | Medium | Any operator could reconcile an UNKNOWN attempt. `confirmed_not_dispatched` refunds the reservation and both dispositions unblock the requirement — a budget- and authority-relevant act by someone outside the capture mandate. | `OperatorResolutionVerifier` accepts only the identity that authorized that workflow. |
| F3 | Medium | Evaluation did not re-verify the stored bytes. Swapping the stored capture after acquisition still allowed an evaluation bound to the original digest (the GET refused to serve it, but the POST did not care). The contract requires every use to re-hash. | `record_evaluation` takes a mandatory `verify_artifacts` callable, run inside the transaction; the API passes the repository's read-time verification for capture and annotation. |
| F6 | Medium | After reconciling a failed SAM phase, the workflow became `failed` and its *completed* capture could no longer be evaluated — volatile evidence already preserved was effectively discarded, forcing a recapture that may no longer be possible. | `failed` workflows with a completed capture are evaluable (without an annotation); `active`/`unknown` never are. The UI offers evaluation for them too. |
| F4 | Medium | Raw captured images and SAM output were served to anyone who could reach the API. | Both GETs require a proven operator token; the UI fetches the image as an authenticated blob. |
| F5 | Medium | The anonymous dev reset — extended in this branch to delete acquisition records — let any caller wipe the acquisition audit trail. | When acquisition is enabled, reset requires an operator token. With acquisition disabled it stays as before. |
| F7 | Low | Any operator could close a requirement as unresolvable. | Only `responsibility.owner` may abstain. |
| F8 | Low | A self-evaluation overwrote an earlier `reported_done_by`, erasing who claimed it first. | The earlier claimant is kept; the self-evaluation remains in the evaluation table and the activity log. |

## Residual risks — accepted, not fixed here

- **Metadata reads are unauthenticated.** `GET /acquisition` returns proposals, capture instructions, evaluator names and rationales, same as the Level 1/2 read endpoints (`red-team-api-and-frontend.md`). Run the API on localhost only; do not expose it on a network.
- **Other dev routes stay anonymous** (tamper, revoke, unresolve). Pre-existing; `KRAKADYL_ENABLE_DEV_ROUTES=0` disables them.
- **Shared-secret identity.** Tokens have no expiry, rotation, or MFA. One person configured under two identities can verify their own capture; the deployment configuration is trusted for that.
- **F1 compares the question and answer classes only**, not the predicate wording or the set of dependent hypotheses. A new hypothesis does not make a capture irrelevant; a predicate rewrite that keeps the same question is treated as the same need. Revisit if predicates start carrying meaning that the question does not.
- **CONTRADICTS leaves the route open** (decision D2 in `level3-case-wiring.md`).
- **Any operator can propose and authorize**; a non-principal's grant can never dispatch (the gate refuses it with nothing persisted), so the harm is clutter, not authority.

## Verification

- `tests/test_red_team_level3.py`: 9 tests; 8 observed failing against commit `51025ac` for the reasons in the table above (DID NOT RAISE / 200 instead of 409 or 401 / 409 instead of 200 / wrong claimant), all passing after the fixes. Full suite: 270 passed.
- Browser (Chromium, fake SAM transport, no Meta call): authenticated image and SAM box overlay render and line up with the captured region; the dev reset shows a 401 without a token, keeps the acquisition history, and succeeds with one.
