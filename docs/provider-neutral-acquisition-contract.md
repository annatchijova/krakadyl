# Provider-neutral acquisition contract

Status: design contract plus an offline coordinator implementation. It does not enable a production acquisition path, select a source or evaluator, authorize SAM, or validate Level 3.

## Observation and baseline

The current core represents `Observation` and `EvidenceRequirement`; the SQLite store persists generic case objects, nonces, and events. There is no acquisition attempt lifecycle, durable budget ledger, acquisition endpoint, or provider adapter. The Level 3 contract already requires exact-scope authorization, atomic pre-dispatch reservation, immutable observations, separate annotation and inferential checks, and abstention when a result is insufficient.

The first runtime slice will define the provider boundary and exercise it with synthetic, local fixtures. It will not connect that path to the API or to existing hypothesis/evidence status transitions.

## Threat model

- An untrusted caller can submit malformed, stale, oversized, or replayed proposal data.
- A source adapter can return substituted, truncated, or mislabeled bytes.
- A processor can return empty, malformed, convincing, irrelevant, or false annotations; its output is data, never instruction or authority.
- The process can crash before dispatch, after dispatch, or before recording the result; concurrent requests can reuse a grant or exceed a budget unless the store rejects them atomically.
- This slice does not defend against a compromised host, database administrator, trusted identity provider, or storage device. It does not claim that a SHA-256 digest establishes truth or acquisition authority.

## Responsibility boundary

| Port | Owns | Must not do |
|---|---|---|
| `EvidenceSource` | Acquire the exact authorized resource and return original bytes plus source metadata | Interpret evidence, change requirements, or assert authorization |
| `EvidenceProcessor` | Derive a candidate annotation from the verified observation bytes | Acquire authority, overwrite the source observation, or decide whether a hypothesis is supported |
| `AuthorizationGate` | Verify trusted authorizer identity and exact-scope grant; atomically compare current need/mandate state, consume the grant once to create a workflow, and reserve the full approved workflow ceiling | Accept caller-asserted identity or model output as proof; consume the grant again for later phases |
| `ArtifactRepository` | Store original artifacts write-once by content digest and recheck the digest on every read used downstream | Replace an existing artifact or treat a digest as proof of truth |
| `EvidenceEvaluator` | Produce a separately attributed evaluation against a named requirement and criterion | Be called implicitly by the source/processor or mutate hypothesis status |

`EvidenceSource` and `EvidenceProcessor` are separate interfaces. SAM 3.1, if later approved, is an `EvidenceProcessor`; it is not a capture source, authorizer, custodian, or evaluator.

## Records and lifecycle

All persisted records carry a schema version. Digests use one canonical, versioned encoding for structured records and SHA-256 for artifact bytes. Amounts and resource usage are integers in declared units; floats are prohibited in limits, reservations, and sealed records.

Every persisted record below carries an explicit `case_id`. Every foreign reference must resolve within that same case; cross-case IDs are rejected before state changes. Each record also carries a schema version.

The contract uses these linked records:

- `AcquisitionNeedSnapshot`: case ID, open requirement ID and revision, linked hypothesis IDs, discriminating question, allowed answer classes, and need-state digest.
- `RetentionDecision`: case ID, policy ID/version, covered data categories and processing destination, permitted retention period, required disposition, and decision authority. It binds to the proposal and is copied by reference/version into each attempt and artifact record. Missing, expired, or out-of-scope policy means no transfer or capture.
- `ProcessingPlan`: case ID, processor capability and allowed model/version, versioned prompt/template, canonical parameters, permitted input transformation, a rule limiting input to the artifact produced by this workflow's authorized source, destination, finite per-phase usage ceiling, and retention/data-handling decision. It is either fully bound into the proposal digest or absent; no processor call is allowed when it is absent. The artifact digest is materialized only after capture and must be supplied by the coordinator from the verified `AcquiredObservation`, never by the caller.
- `AcquisitionProposal`: case ID, need snapshot, source ID and capability revision or lease, exact capture specification, expected discriminating outcomes, optional exact `ProcessingPlan`, mandate ID/revision, finite limits scoped per requirement, case/mandate, and deployment/account, and a versioned retention decision.
- `AcquisitionAuthorization`: case ID, unique grant ID, trusted authorizer identity and authentication basis, exact proposal digest, need-state digest, mandate revision, scope, retention decision version, issue time, and expiry. It authorizes one immutable workflow and is consumed once at workflow creation; it cannot be reused to create another workflow.
- `AcquisitionWorkflow`: case ID, store-derived unknown-lock key, proposal/grant links, phase state, reservation ID, reserved and actual aggregate resource usage, timestamps, and reconciliation status. The store derives the lock key from the verified case ID and requirement ID using the versioned canonical encoder; callers cannot submit or override it. A durable uniqueness rule allows no second active workflow for that case/requirement while an earlier workflow is unknown.
- `AdapterAttempt`: case ID, workflow/proposal/grant links, phase (`SOURCE_CAPTURE` or `PROCESSOR_DERIVATION`), state, exact canonical request record/reference and digest, reservation ID, reserved and actual resource usage, retention decision version, timestamps, provider request ID when available, and failure/unknown-outcome reason.
- `AcquiredObservation`: case ID, original content-addressed artifact reference and digest, source/capability version, acquisition time, actor, custody metadata, and the retention policy/version and disposition governing the artifact.
- `AnnotationCandidate`: case ID, exact observation ID/digest, processor and model version, exact canonical request or immutable request reference plus digest, prompt/template version, raw output digest/reference, measured usage, and retention policy/version and disposition. The candidate remains untrusted derived data.
- `EvidenceEvaluation`: case ID, requirement and evidence/annotation versions, evaluator identity/type, criterion/version, one explicit categorical outcome, rationale, timestamp, and retention policy/version. It is stored separately; this slice does not translate it into a hypothesis status.

Each source or processor invocation is its own `AdapterAttempt`; completion means only that one named phase's response and actual usage were durably recorded. It does not mean that the entire workflow, annotation validation, or inferential evaluation completed. One authorization creates one immutable workflow and is consumed exactly once there. The workflow transaction reserves the maximum usage for every authorized phase against all aggregate scopes. Later phase gates validate the workflow's already-consumed grant, phase order, immutable plan, current versions, and that phase's allocation; they do not consume the grant a second time. A future design that wants separate approval for processing must use a distinct processing grant and reservation, not reuse the capture grant.

At workflow creation, one durable compare-and-consume transaction must verify current case/need and mandate revisions, grant scope and expiry, the retention decision, source and processor plans, and finite limits. It consumes the grant, creates the workflow, and reserves maximum usage against all applicable per-requirement, per-case/mandate, and deployment/account ceilings. Reservations include in-flight work and count across workers and restarts. Before each phase, a durable transaction checks the current workflow and plan, commits its attempt's dispatch intent, and binds the exact outgoing request to the approved plan. Each adapter capability version/lease must remain valid at workflow commit, or that adapter must enforce scope and authority at actual dispatch; if neither can be established, the operation abstains.

Before each external adapter invocation, its attempt must durably transition from `RESERVED` to `DISPATCH_INTENT`. No adapter invocation may occur before that transition commits. The exact outgoing processor request is canonicalized and checked against the approved `ProcessingPlan` (including model/version, prompt/template version, parameters, input digest, destination, and usage ceiling); any mismatch is rejected before the adapter is called. On recovery, `RESERVED` with no dispatch intent can be closed as `FAILED_BEFORE_DISPATCH` only if the implementation makes dispatch before that transition impossible. `DISPATCH_INTENT` without a durably recorded response is `UNKNOWN_AFTER_DISPATCH`, even if the crash may have occurred before bytes left the process; this conservative state prevents a duplicate side effect. Keep the full workflow reservation and block every later dispatch for the same case/requirement while any source or processor attempt is unknown. The trusted store derives this lock from the verified requirement; a new proposal ID, grant ID, source specification, or caller-supplied key cannot bypass it. Reconcile with the adapter or record an authorized manual disposition before another workflow for that case/requirement can be considered. No automatic retry or refund is permitted while outcome is unknown.

A confirmed pre-dispatch failure may release only the reservation for work proven not to have started; the consumed authorization remains consumed. A partial capture never becomes an `AcquiredObservation`. It may be preserved only in a restricted quarantine when the already-bound retention decision permits it; otherwise the source operation must not begin without a defined partial-artifact disposition.

The exact processor request (provider/model identifier and version, prompt or template version, media reference/digest, and options) is stored as a canonical immutable request record or content-addressed reference. Its digest alone is not a substitute for the request. Credentials and unrelated secrets are excluded from that record. The retention decision governing the request, transfer, original, and derivative is separately recorded; an implementation may not infer retention from a provider name or pricing mode.

## Offline implementation boundary

The offline implementation provides typed records, protocols, a coordinator, and synthetic test adapters. Adapter output is a readable binary stream. The coordinator reads at most 64 KiB per call, requests no more than the remaining byte ceiling plus one byte, caps read calls, checks elapsed time around each read, and closes the stream on success or failure. Production stream adapters must honor the requested read size at the transport boundary; the coordinator detects an over-return but cannot undo memory already allocated by a defective adapter. Because stream reads and adapter calls are synchronous, the concrete transport adapter must enforce a socket/request timeout; this coordinator cannot interrupt a blocked `read()` or adapter call. The coordinator buffers no more than the authorized artifact limit (plus a bounded read chunk and the final immutable byte copy). Resource counters reject booleans and non-integer values. Structured JSON is limited to 64 KiB, depth 32, and 4,096 nodes; free-text questions and prompts are limited to 16 KiB.

This slice supports only `identity-bytes` as the processor input transformation and includes that choice in the immutable processor request. Other transformations are rejected before workflow creation. The original observation links to its source attempt. Exact request records are persisted with the retention decision passed to the request repository; a production repository must enforce its expiry and disposition for those records as well as artifacts.

Synthetic adapters are test-only and cannot be enabled through production configuration. Test adapters use generated fixture bytes only. This module has no authenticated authorization gate, durable reservation implementation, immutable production artifact repository, configured aggregate limits, retention enforcement, identified evaluator, or production source/processor adapter. The runtime must fail closed when these components are absent. A test fake can demonstrate coordinator behavior; it cannot establish production authentication, cross-process budget enforcement, crash durability, retention compliance, or real source capability.

No concrete identity mechanism, acquisition source, evaluator authority, numerical limits, vendor mode, retention selection, or paid call is chosen by this contract. These remain explicit deployment gates. In particular, passing an offline SAM-like fake does not authorize Meta API use.

## Falsifiers and required tests

The design is wrong if any of these can occur:

1. A missing, expired, mismatched, replayed, or caller-asserted grant reaches the source or processor.
2. A need, mandate, retention decision, source/processor capability, or processing-plan revision changed before dispatch and the old grant still dispatches; or an adapter fails to enforce its bound lease/scope at dispatch.
3. Two concurrent requests consume the same authorization or reserve beyond any per-requirement, per-case/mandate, or deployment/account ceiling, including in-flight reservations.
4. A crash after `DISPATCH_INTENT` leads to refund, automatic retry, or another dispatch for the same case/requirement before reconciliation, including when the caller supplies a new proposal, grant, or lock key.
5. A persisted reference points across cases, a source replaces bytes under an observation reference, or a later read skips digest verification.
6. Processor output, including a plausible false annotation, changes requirement or hypothesis status without a distinct evaluation record.
7. Empty or non-discriminating output is treated as a negative finding or successful resolution.
8. The processor request differs from its authorized model/version, prompt/template, parameters, input scope, destination, or usage cap and still reaches the adapter; or the exact request/retention decision cannot be reconstructed from its versioned immutable record.
9. A partial capture is exposed as a complete observation or retained/deleted without applying the bound retention disposition.
10. A processor phase is attempted more than once under one workflow, or is blocked despite remaining within the immutable workflow plan and its still-reserved allocation; the human grant is consumed exactly once when the workflow is created and cannot create a second workflow.
11. A processor request changes the model, prompt, parameters, input artifact, destination, or ceiling after approval and still reaches the adapter; or a valid later phase cannot run once under its existing workflow without re-consuming the grant.

Tests must use synthetic fixtures and a fake clock; assert persisted state and adapter call effects, not mock return values. At least one negative control must show each key gate rejects when removed or inverted. No test in this slice calls Meta or transmits case data.

## Decision and reconsideration

The source/processor split is chosen over a provider-centered interface because the system must preserve an authorized observation even when annotation is unavailable, wrong, or inconclusive. A single `SAMAdapter` that captures, interprets, and resolves a requirement would collapse custody, derived annotation, and inference into one trust boundary. A set of uncoordinated protocols without an atomic authorization/reservation gate is also insufficient because it cannot constrain dispatch under replay, concurrency, or crash.

Revisit this design if a concrete source cannot meet the interface, the README responsibility boundary changes, or a named evaluator is granted a different documented authority. Evidence that would falsify the choice includes a real-source workflow that cannot preserve original bytes and source provenance separately from processing, or a concurrency/crash test that demonstrates the gate does not enforce its transaction contract.

## Red-team disposition

Independent live-code review found and this slice addressed: unbounded byte-stream work; an approved non-identity transformation that was not applied; local artifact verification occurring after processor dispatch intent; request persistence without its retention decision; and observations without their source-attempt link. Falsifiable tests now cover over-limit streams, the source attempt link in the accepted observation, pre-dispatch artifact failure, strict integer input, and rejection of unsupported transforms. The reviewer also identified that synchronous adapters can block inside a call or `read()`; the coordinator checks elapsed time around reads and closes streams, but only a concrete transport adapter can enforce cancellation/timeouts while blocked.

The in-memory gate and repositories in tests are behavioral fakes. They do not test transaction atomicity, aggregate reservations across workers, crash recovery, or the true case/requirement unknown-lock uniqueness rule in a production database. Those remain implementation gates, not completed guarantees. Structured request size/depth bounds are enforced in the offline record constructors; no API route currently exposes these records.

Skills applied: `secure-by-construction`, `software-archaeology`, `atomic-state-mutation`, `distributed-write-atomicity`, `versioned-schema-evolution`, `falsifiable-testing`, `red-team-auditing`, `git-discipline`, `claim-provenance-discipline`, `data-provenance-mapping`, `surgical-patcher`, `destination-driven-construction`, `resource-exhaustion-review`, and `validate-at-the-boundary`.
