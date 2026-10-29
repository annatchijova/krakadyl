# SQLite acquisition gate design

Status: implementation contract for a local SQLite lifecycle gate. This design does not add an API route, production identity provider, source adapter, processor adapter, or paid provider call. The gate must not be instantiated for production until its injected authorization and scope policies have reviewed implementations.

## ADR-001 — Keep the acquisition gate local and policy-injected

Date: 2026-10-29. Status: proposed. Reversibility: one-way-ish, because SQLite tables and persisted lifecycle records need a migration to change after use.

### Forces at the time

KRAKADYL now has a provider-neutral coordinator and contract, but no trusted login, signed grant format, current mandate-to-source mapping, production retention policy store, or reliable provider billing meter. The existing API principal is caller-asserted. The current store is a local SQLite database and the acquisition module is not connected to an API route.

### Decision

Implement only SQLite-backed lifecycle and budget transitions. Require explicit, no-default verifier and policy dependencies. Keep the coordinator unreachable from the API until concrete implementations establish trusted identity, scope, current state, retention, revocation, and budget policy. Use `BEGIN IMMEDIATE` with unique database constraints as the admission/phase linearization point. Treat a completed phase's maximum approved usage as committed upper-bound spend until an authoritative meter exists.

### Alternatives rejected

- **Trust the submitted `authorizer_identity` or current HTTP `principal`** — rejected because either value is caller-asserted and does not prove who approved the proposal. Best argument: it would make the local demo flow easier to wire.
- **Build a production gate before choosing an authentication and mandate-scope mechanism** — rejected because persistence does not create authority. Best argument: a complete local feature would appear to advance Level 3 more visibly.
- **Persist the request and then separately create dispatch intent** — rejected because a crash can leave a sensitive request without an attempt record. Best argument: it preserves the existing `RequestRepository` boundary with less code change.

### Assumption and consequences

Assumption: SQLite is a supported local database shared by the processes that need to coordinate; this decision does not cover separate hosts or unsupported network filesystems. The conservative budget ledger can overstate actual spend by charging each completed phase at its ceiling. Request row expiry is logical deletion only; WAL, snapshots, and backups need separate retention controls. These limitations are accepted for this branch and must not be described as production authentication, physical erasure, or exact billing.

### Revisit trigger

Reopen this record when KRAKADYL selects a concrete identity proof and mandate-to-source policy, exposes acquisition through an API, needs multi-host coordination, adopts an authoritative billing meter, or requires physical erasure guarantees for SQLite/WAL/backup copies.

### Anchored at

`krakadyl/core/acquisition_store.py` and the corresponding transaction seam in `krakadyl/store.py` should point here where the gate enforces these constraints.

## Observed boundary

`AcquisitionAuthorization` binds a grant ID to an exact proposal digest, but does not itself carry a verifiable credential. The existing HTTP principal is caller-asserted. `EvidenceRequirement` has no revision field, and `Mandate` does not define how source capabilities map to resources and operations. The current `AuthorizationGate` protocol also lacks phase-specific failure and unknown-outcome reconciliation. A SQLite transaction cannot supply any of these missing trust claims.

## Required capabilities

The gate constructor requires, with no defaults:

- An offline `AuthorizationVerifier` that accepts the proposal, authorization, and ephemeral credential proof; verifies the proof against the exact proposal digest; and returns the authenticated identity. The proof is never serialized, persisted, logged, or passed to adapters.
- A bounded, local `AcquisitionScopePolicy` that checks the authenticated identity, current mandate, source/capability, operation, destination, retention scope, and phase. It performs no network I/O while a database transaction is held.
- A `BudgetPolicy` that supplies immutable per-requirement, per-case/mandate, and deployment/account hard caps. Proposal ceilings must not exceed those caps; a caller cannot raise a cap by submitting a larger proposal.
- A `RetentionPolicyProvider` that supplies the current policy decision for case, destination, data categories, policy ID, and version. It is checked at workflow creation and before every phase dispatch.
- An `UnknownResolutionVerifier` for an explicit, retained disposition of an unknown attempt. It cannot authorize an automatic retry.
- A `GrantRevocationVerifier` for authorized grant revocations. Revoked authorization IDs are persisted and checked before every phase.
- A `RecoveryQuiescenceVerifier` whose proof establishes that every prior worker sharing this database has stopped before unresolved dispatch intents can be changed to `UNKNOWN`.
- A stable deployment budget scope configured by the gate. The caller cannot choose the deployment-account key.

Absence of any required capability rejects workflow creation. These interfaces are tested with synthetic fakes only; they are not production authentication or mandate policy.

## Current-state binding

Digest format is fixed for this version: `requirement_revision` is lowercase hex SHA-256 over `canonical_bytes({"digest_type": "acquisition_requirement_revision", "digest_version": 1, "requirement": requirement.model_dump(mode="json")})`. `need_state_digest` is lowercase hex SHA-256 over `canonical_bytes({"digest_type": "acquisition_need_state", "digest_version": 1, "requirement": requirement.model_dump(mode="json"), "hypotheses": [h.model_dump(mode="json") for h in sorted(linked_hypotheses, key=lambda item: item.id)]})`. The existing type-tagged `canonical_bytes` encoder is used and carries `CANONICALIZE_VERSION`. Duplicate hypothesis IDs are rejected. The proposal is rejected if its hypothesis IDs do not exactly match all current hypotheses whose `discriminating_requirement_id` points to the requirement, if a linked record is missing, or if the requirement is resolved, unresolvable, or authority-blocked. A future digest-recipe change increments `digest_version`.

The gate recomputes these values from `objects` during workflow creation and before every phase dispatch. It reloads and checks the current mandate and its time window, retention policy and its `valid_until`, capability policy, and grant-revocation record at each dispatch. Admission stores a canonical SHA-256 digest of the full mandate snapshot; a phase dispatch rejects a mandate whose fields changed even if its revision was not incremented. Schema v3 adds this digest; legacy workflows without it fail closed at dispatch. Persisted gate timestamps are normalized to UTC before ISO serialization so expiry and recovery cutoffs remain chronological across caller offsets. The authorization proof is verified before acquiring the SQLite write transaction; authenticated identity and exact proposal binding are checked again inside it. Revocation stores an authorization ID with a verified revocation record; it does not mutate the signed authorization payload.

`AcquisitionCoordinator.acquire(proposal, authorization, proof)` receives the ephemeral credential proof in memory and forwards it only to `create_workflow(proposal, authorization, proof)` and each `begin_phase(workflow, phase, request, retention, proof)`. Each gate method verifies it before opening the write transaction; the coordinator never places proof bytes or the token in records, request repositories, logs, or adapter calls. The transaction is the authorization linearization point: a revocation committed before `DISPATCH_INTENT` denies that dispatch; a revocation committed after it affects later phases and workflows, not the already-authorized attempt.

## SQLite transaction boundary

`KrakadylStore` provides one bounded callback transaction using `BEGIN IMMEDIATE`, its per-instance connection lock, SQLite `busy_timeout`, rollback on any exception, and no nested store calls from the callback. Every committed dispatch intent increments the persisted `dispatch_generation` in that transaction. A recovery caller obtains the generation with `recovery_generation()` and obtains quiescence evidence that binds to that exact generation. The gate verifies the proof before opening the write transaction, then compares the generation again inside `BEGIN IMMEDIATE` before sweeping unresolved intents. If a dispatch committed after proof issuance but before recovery acquired the lock, the generation differs and recovery rejects the stale proof without changing state. If recovery acquires the lock first, new intents wait until the sweep commits and are not included in it. Schema v4 persists this generation. The verifier must reject replayed or stale proofs and establish that every worker associated with intents through the bound generation has stopped, including workers paused between intent commit and adapter invocation. Versions 1–3 migrate with generation zero; the verifier must also establish quiescence for legacy pending intents because they predate generation tracking. Mixed-version writers that do not increment this generation are outside the guarantee and must be stopped before recovery. SQLite uniqueness constraints enforce one use per authorization ID, one attempt per workflow/phase, and one active or unknown workflow per `(case_id, requirement_id)`. The guarantee covers processes sharing the same supported SQLite database file; it does not claim coordination across separate hosts or unsupported network filesystems.

The coordinator passes the exact request record and retention decision directly to `AuthorizationGate.begin_phase()`. The gate inserts the request record, content-addressed reference, and `DISPATCH_INTENT` attempt in the same transaction; `RequestRepository.put_request()` is removed from this coordinator path. This avoids an orphaned sensitive request when request persistence and dispatch intent would otherwise be separate writes. Expiry removes a request row logically; it does not prove physical erasure from SQLite WAL files, filesystem snapshots, or backups. Those copies remain subject to separate deployment retention controls and outside this branch's guarantee. The attempt retains the request digest and reference after the request body expires.

## Reservation and transition rules

The workflow reserves the sum of all approved phase ceilings against `(case_id, requirement_id)`, `(case_id, mandate_id)`, and the gate-configured deployment scope in one transaction. For each dimension, the effective hard cap is the lower of the exact grant ceiling and matching immutable `BudgetPolicy` cap; a proposal above policy is rejected. Each scope checks committed upper bounds plus outstanding reservations before admission. Reservation rows are durable and include in-flight work.

If workflow creation commits but a phase is denied or fails before its `DISPATCH_INTENT`, `abort_before_phase_intent(workflow_id, phase, reason)` may terminalize the workflow. It verifies under `BEGIN IMMEDIATE` that the named phase has no dispatch intent and that all required predecessor phases are completed. The coordinator invokes it when `begin_phase` fails before committing intent; recovery may invoke it after the configured stale age for an abandoned workflow with no pending intent. Converting a durable dispatch intent to `UNKNOWN` requires proof from `RecoveryQuiescenceVerifier` that all prior workers are stopped; a process restart by itself does not prove that another process is not still inside an adapter call. Terminalization preserves completed upper-bound charges and releases the failed and later unstarted ceilings. No grant is restored or workflow reused.

Abort and `begin_phase` serialize through the same SQLite write transaction. If abort commits first, `begin_phase` observes the terminal workflow and rejects; if phase intent commits first, abort observes the intent and cannot use the pre-intent abort path. The coordinator calls an adapter only after `begin_phase` returns the matching committed intent, so an aborted workflow cannot dispatch afterward.

Adapter-reported `actual_usage` is retained for audit but is not a trusted billing meter. On confirmed completion, the full phase ceiling moves from reserved to committed upper-bound usage. On `UNKNOWN_AFTER_DISPATCH`, the phase ceiling remains reserved and the requirement lock remains held. A proven pre-dispatch failure terminalizes the workflow: it preserves committed upper bounds for completed phases, releases the failed phase and every later phase that never reached dispatch, removes the active requirement lock, and consumes the original grant permanently. Continuing requires a new grant and full admission checks. This may under-utilize the budget, but cannot create budget by trusting an adapter's understated cost.

An unknown attempt can be cleared only by a verified `UnknownResolution` record. `CONFIRMED_NOT_DISPATCHED` releases that phase's reservation; `ACCEPTED_AS_UNKNOWN` preserves the full phase upper-bound charge and records an explicit operator decision before unlocking. Either terminal disposition releases ceilings for later phases that never reached dispatch, while retaining committed ceilings for completed phases. The workflow becomes terminal and cannot be reused; another workflow requires a new authorization ID and fresh admission checks. A resolution cannot be inferred from a timeout, caller retry, new grant, or adapter-reported zero usage. No automatic retry or refund is performed.

Coordinator validation failures after a gate has committed `DISPATCH_INTENT`, but before adapter invocation, must call `fail_attempt_before_dispatch(workflow_id, phase, request_digest, reason)`. This trusted composite key identifies the exact just-created row even if the returned `AdapterAttempt` has a malformed attempt ID or other field. The gate verifies the row belongs to the workflow, phase, and exact request digest, proves it is still at dispatch intent, and atomically terminalizes the workflow before releasing only unstarted reservations. No other attempt may be affected.

`reset_case()` does not delete acquisition workflows, attempts, request digests, unknown locks, or budget ledger rows. Demo reset cannot erase acquisition history or release an unknown lock.

## Falsifiers

1. Two store instances race the same grant: exactly one workflow is created.
2. Two grants race the same `(case, requirement)`: at most one active/unknown workflow exists; distinct cases and distinct requirements do not collide.
3. Two workers race against a remaining budget smaller than either reservation: at most one is admitted, and the sum never exceeds any scope.
4. Injected failure after each SQL write leaves no partial workflow, attempt, reservation, lock, or request row.
5. A mandate, requirement, linked hypothesis, processing plan, retention policy, capability, or grant revocation changes between phases: the next dispatch is denied.
6. An unknown attempt survives store close/reopen and cannot be bypassed with new proposal/grant IDs; only a verified resolution changes the lock.
7. Setting adapter-reported USD usage to zero never reduces a committed upper bound or creates new budget.
8. Mutating each field of an `AdapterAttempt` returned after `DISPATCH_INTENT` (including its ID) cannot redirect pre-dispatch closure: the exact `(workflow_id, phase, request_digest)` row is terminalized before adapter invocation; only unstarted phase ceilings are released, completed phase upper bounds remain committed, and a new workflow is required.
9. Expired request rows are logically removed while their attempt digest, reference, retention metadata, and event trail remain. No physical-erasure claim is made for WAL, snapshots, or backups.
10. A proposal ceiling above an immutable scope cap is rejected; concurrent reservations never exceed a configured cap even if callers submit larger values.
11. Changing the digest recipe version or canonical record schema changes the digest; duplicate hypothesis IDs and non-canonically ordered hypothesis tuples are rejected, so permutations cannot create another representation of the same need.
12. The ephemeral proof passed to `acquire()` reaches only the injected verifier and never appears in persisted records, request bodies, logs, adapter arguments, or raised errors.
13. A workflow abandoned after creation but before its first dispatch can be recovered after store reopen: all unstarted reservations and its lock are released, the grant remains consumed, and no adapter is called.
14. A later phase denied before its own intent after an earlier phase completed terminalizes the workflow, preserves completed phase charges, releases the denied and later unstarted phase ceilings, removes the lock, and makes no adapter call for the denied phase.
15. A race between pre-dispatch abort and `begin_phase` has one serialized winner: either the workflow is terminal with no intent, or the attempt is committed at dispatch intent; never both, and no adapter call follows a committed abort.
16. An expired mandate or retention decision is rejected by the gate even when synthetic policy fakes permit it; caller time-zone offsets cannot change expiry or stale-age outcomes.
17. A live dispatch intent cannot be converted to `UNKNOWN` without verified global worker quiescence; an invalid proof leaves workflow, attempt, and reservation state unchanged.
18. A same-revision mutation to any persisted mandate field after admission is rejected before dispatch and creates no attempt.
19. A dispatch committed while quiescence proof verification is in progress increments the shared generation; recovery rejects the stale proof and leaves all attempt states unchanged.
20. If recovery acquires `BEGIN IMMEDIATE` first, a concurrent new dispatch waits; recovery sweeps only the intents covered by the proof generation, then the new dispatch commits and remains `DISPATCH_INTENT`.

## Explicitly not established by this branch

There is no concrete credential issuer/verifier, mandate-to-source mapping, evaluator, provider, API integration, remote database, or production budget policy. The injected fakes prove only SQLite lifecycle and transaction behavior. No real evidence or paid service is used.

The coordinator's `duration_ms` ceiling is checked after synchronous adapter calls and stream reads return. It rejects an overrun but cannot interrupt a blocked call. Every concrete adapter must enforce its own transport and read timeouts before it is enabled; this local coordinator does not provide a hard execution deadline.

Skills applied to this design: `software-archaeology`, `secure-by-construction`, `atomic-state-mutation`, `concurrency-reasoning`, `distributed-write-atomicity`, `falsifiable-testing`, `audit-before-patch`, `data-provenance-mapping`, `destination-driven-construction`, `red-team-auditing`, `versioned-schema-evolution`, and `surgical-patcher`.

Skills applied to the provider-correlation and duration-contract follow-up: `audit-before-patch`, `surgical-patcher`, `diagnosing-bugs`, `falsifiable-testing`, `red-team-auditing`, `invariant-hunting`, `concurrency-reasoning`, `distributed-write-atomicity`, `resource-exhaustion-review`, and `git-discipline`.
