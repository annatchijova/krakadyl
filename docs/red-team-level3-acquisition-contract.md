# Red-Team Review — Level 3 Acquisition Contract

- **Date:** 2026-10-28
- **Method:** Abductive Engineering (A–D–I), Red-Team Auditing, and invariant tracing
- **Scope:** `docs/level3-acquisition-contracts.md`, its Level 3 roadmap link, and current identity/storage boundaries cited to evaluate the contract. No Level 3 runtime path exists in this scope.
- **Base reviewed:** `docs/level3-acquisition-contracts` at `bb599665d926c4ac89817dee4092a2e0619db994`
- **Reproducible evidence:** live source review and contract falsifiers; no Level 3 runtime experiment was possible because no acquisition implementation exists.

## Threat model

- **Attacker CAN:** submit and replay API request bodies; choose caller-asserted identity fields; issue concurrent requests and retry after timeouts; provide malformed, irrelevant, or misleading sensor results.
- **Attacker CANNOT:** modify server code, directly write the trusted database, or access a properly scoped authentication credential.
- **Trust boundary:** caller and sensor output to KRAKADYL's authorization, durable attempt ledger, evidence store, and any external paid processor.

## Epistemic legend

CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## Executive summary

| ID | Potential impact if realized | Evidence level | Module | Finding |
|---|---|---|---|---|
| L3-A1 | Unauthorized acquisition if caller-asserted identity is trusted | CODE FACT + future-path hypothesis | Authorization contract / API identity | The contract said “human authorization” without requiring an authenticated authorizer; the current API only compares a caller-asserted principal. |
| L3-A2 | Spend ceiling can be exceeded under concurrent calls | PLAUSIBLE HYPOTHESIS | Paid-call budget reservation | Durable counters alone can be exceeded by concurrent requests unless in-flight cost is atomically reserved. |
| L3-A3 | Duplicate spend and missing attempt history | PLAUSIBLE HYPOTHESIS | Attempt lifecycle | A crash or timeout after dispatch can leave an externally billed operation with no durable result; retry can duplicate it. |
| L3-A4 | A consumer could analyze bytes different from the recorded observation | PLAUSIBLE HYPOTHESIS | Observation storage | A digest identifies bytes but does not itself make the stored artifact immutable or ensure later reads match it. |
| L3-A5 | A stale authorization could dispatch after mandate or evidence state changes | CODE FACT + future-path hypothesis | Authorization lifecycle | Existing action paths revalidate after waits and before execution; the original acquisition contract did not require a pre-dispatch state check. |

## Findings

### L3-A1 — Caller-asserted identity could satisfy “human authorization”

- **Potential impact if implemented this way:** Unauthorized acquisition through an endpoint exposed to an untrusted caller.
- **Epistemic level:** CODE FACT about current identity handling; PLAUSIBLE HYPOTHESIS about a future Level 3 endpoint.
- **Bucket:** Trust-boundary design gap, not a demonstrated acquisition vulnerability.

- **Surprise / expectation violated:** the original contract required exact-scope human authorization but did not specify how the authorizer's identity is authenticated.
- **Abduction:** a future implementation might treat `principal` from a request body as proof of the human authorizer.
- **Deduction:** if so, an unauthenticated caller can claim the mandate principal and satisfy the authorization check.
- **Source verification:** `_assert_principal` compares the body value with `mandate.principal`; `api/app.py` and `docs/red-team-api-and-frontend.md` explicitly state that this is caller-asserted identity, not authentication. No Level 3 endpoint exists, so acquisition reachability was not demonstrated and no acquisition exploit was run.
- **Rival explanation:** “human authorization” might have implied authenticated identity. That reading is not safe here because the repository documents the missing authentication layer directly.
- **Disposition:** the contract now requires a distinct, single-use authorization tied to the case, complete proposal and need-state digest, mandate revision, expiry, and an identity from trusted authenticated context. Without verifiable identity, acquisition must abstain.

### L3-A2 — Concurrent calls can over-reserve a durable budget

- **Potential impact if implemented with a non-atomic read-then-call path:** concurrent requests could exceed the authorized spend ceiling.
- **Epistemic level:** PLAUSIBLE HYPOTHESIS; no Level 3 budget code exists to execute.
- **Bucket:** Future concurrency design risk, not a current runtime vulnerability.

- **Invariant:** `spent + in_flight_reserved <= configured_limit` across every worker sharing the account or case budget.
- **Abduction:** two requests may each read the same remaining balance and both decide to call.
- **Deduction:** with capacity for one request, two concurrent requests can each pass a prior check and jointly exceed the cap unless reservation and accounting are atomic.
- **Falsifier:** a storage-level atomic reservation under concurrent callers permits at most the remaining bounded capacity, and a denied caller makes no external request.
- **Disposition:** the contract now requires one atomic durable compare-and-consume transaction to consume authorization, create the attempt, and reserve maximum bounded cost/resources across requirement, case/mandate, and deployment/account ceilings.

### L3-A3 — Timeout/crash after dispatch makes retry safety unknowable

- **Potential impact if an unknown outcome is retried automatically:** duplicate spend and a broken attempt trail.
- **Epistemic level:** PLAUSIBLE HYPOTHESIS; no Level 3 dispatch or persistence path exists to execute.
- **Bucket:** Distributed side-effect recovery risk, not a current runtime vulnerability.

- **Invariant:** a paid call that may have left the process is never silently forgotten, refunded, or repeated while its outcome is unknown.
- **Abduction:** the process may die after the vendor receives the request but before KRAKADYL persists the response.
- **Deduction:** after restart, a naive retry can duplicate billed work; dropping the attempt can understate spend and erase the custody trail.
- **Falsifier:** kill or timeout at each dispatch boundary and observe a durable unknown state, retained reservation, and no automatic second call before reconciliation.
- **Disposition:** the contract now requires persisting the attempt and reservation before dispatch, then recording unknown outcome without automatic retry or refund until reconciled.

### L3-A4 — A digest alone does not enforce immutable observation storage

- **Potential impact if storage can be replaced or reads are not checked:** consumers could analyze bytes different from the recorded observation.
- **Epistemic level:** PLAUSIBLE HYPOTHESIS; no new observation storage path exists to execute.
- **Bucket:** Evidence-integrity design risk, not a demonstrated bypass.

- **Invariant:** bytes retrieved for an observation have the recorded digest and cannot be replaced under the same identity without a detectable failure.
- **Abduction:** storing a digest beside a mutable path without verifying reads permits the bytes and digest to diverge.
- **Deduction:** a later consumer may analyze replacement bytes while referring to the original observation ID.
- **Falsifier:** replace the stored bytes after acquisition; all subsequent reads or derivations must reject the mismatch and preserve the original artifact reference.
- **Disposition:** the record contract now requires a write-once or content-addressed reference plus digest verification on every read used for display, analysis, or derivation; a mismatch blocks use and records an integrity failure. Runtime enforcement remains unimplemented.

### L3-A5 — Authorization and acquisition need can decay before dispatch

- **Potential impact if stale state is used:** a paid observation could be acquired after its mandate was revoked, expired, or its discriminating requirement had changed.
- **Epistemic level:** CODE FACT about existing revalidation patterns; PLAUSIBLE HYPOTHESIS about an absent Level 3 path.
- **Bucket:** Authorization-decay design risk, not a demonstrated Level 3 vulnerability.

- **Invariant:** the current case, requirement, source-capability basis, and mandate state at acquisition dispatch must be the state authorized by the human.
- **Abduction:** an implementation may validate the proposal only when it is created or approved, then dispatch later from that stale decision.
- **Deduction:** if the requirement resolves, the source becomes unavailable, or the mandate expires/revokes before dispatch, a call using the old approval still occurs unless state is revalidated at the effect boundary.
- **Source evidence:** the existing executor rechecks current mandate and evidence before execution. The Muse endpoint reloads the mandate and principal after its external call, and the test source defines a revocation-during-call check. No Level 3 acquisition path exists to run.
- **Rival explanation:** binding the proposal to a mandate revision may imply revalidation, but binding alone does not prove the revision is still current at dispatch.
- **Disposition:** the contract now requires a durable compare-and-consume transaction that checks current case/need/mandate state and a proposal-bound source-capability version or lease, and defines that commit as the authorization linearization point. If source capability cannot be versioned, leased, or checked by the source at dispatch, the workflow abstains. A change committed earlier blocks dispatch; a later revocation cannot recall an already authorized request.

## Discarded vectors

| Vector | Result | Why it did not survive as a current finding |
|---|---|---|
| Empty SAM result treated as a negative case finding | Rejected by the contract; runtime behavior untested | The contract explicitly records empty output as a valid model result, not a negative finding or requirement resolution. No runtime path was tested. |
| Valid mask promoted directly to verified identity, custody, or causation | Rejected by the contract; runtime behavior untested | The contract explicitly keeps SAM output as an untrusted derived candidate and separates integrity, annotation validation, and inference. No runtime path was tested. |
| Changed proposal reuses old authorization | The contract now forbids it; runtime behavior untested | Authorization is single-use and bound to the complete proposal and need-state digest, case, and mandate revision. Implementation still needs an executable test. |
| Cross-case record substitution | Addressed as a missing binding in this review | The record table now requires explicit case IDs and same-case reference validation. This remains a runtime acceptance test, not an executed proof. |

## Recommendations not implemented

- Select the actual authentication mechanism and define how an authorization is verified outside request-body fields.
- Select a named inference evaluator and define who may author or accept an `EvidenceEvaluation`.
- Set finite attempt, file-size, frame-count, duration, concurrency, and monetary limits before enabling any paid adapter.
- Verify vendor retention, training, and processing terms at implementation time; use sanitized evidence only after explicit data-scope approval.
- Implement crash-injection and concurrent-reservation tests before the live SAM closing experiment.

## Verification boundary

This review changed contract requirements only. It did not demonstrate a Level 3 exploit or prove a future adapter safe. Earlier repository verification covered the unchanged runtime: 102 non-API tests passed; the HTTP regression smoke passed through Uvicorn; the full `TestClient` suite remained blocked by the environment. Those runs do not validate these future Level 3 requirements. No candidate in this review is labeled CONFIRMED BY INDUCTION because no Level 3 runtime path was available to execute.

## Skills used

`red-team-auditing`, `invariant-hunting`, `audit-before-patch`, `beyond-the-fix`, `discriminating-proof`, `concurrency-reasoning`, `atomic-state-mutation`, `surgical-patcher`, and `git-discipline`.
