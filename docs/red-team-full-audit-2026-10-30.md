# Full Red-Team Audit — 2026-10-30

## Scope and epistemic discipline

This audit covers the live `main` tree at commit `21be5cf` after the ordered
Level 3, Level 4, and Level 5 merges and the bearer-authentication round. The
threat model is an HTTP caller who
can reach the API, can submit arbitrary JSON and case identifiers, and may hold
one configured operator bearer token. OS-level database or source modification
is out of scope.

Claims below use these levels:

- **CODE FACT** — verified in the live source.
- **CONFIRMED BY INDUCTION** — the predicted behavior occurred in a controlled run.
- **PLAUSIBLE HYPOTHESIS** — the source chain is credible but the end-to-end
  interaction was not induced.
- **FALSIFIED** — the proposed behavior did not survive the test.

## Test evidence

- The earlier baseline run recorded `344 passed` with
  `tests/test_laya_adapter.py` excluded. A later rerun is not certified green:
  the local Python/AnyIO worker-thread path hangs even in a minimal FastAPI
  application, so the HTTP suite was not counted as passed in this round.
- Direct induction probes for RT-AUTH-01 through RT-RESOURCE-01 ran in fresh
  temporary databases and are recorded under each finding.
- `python3 -m compileall -q krakadyl demo tools`: passed.
- Frontend `npm run build`: passed.
- Frontend `npm run lint`: passed with one existing React warning at
  `frontend/src/App.tsx:44`.

## Findings and prior remediation

### RT-HANDOFF-01 — acceptance did not fence the full case state

Impact: an accepted handoff could report that no state changed even when an
unrelated requirement changed after the handoff was recorded.

Severity: **medium demonstrated**. The test does not demonstrate unauthorized
capture or export; it demonstrates an integrity and audit-trail fracture in a
multi-operator transition.

Invariant:

```text
accepted.state_changed_since_handoff ==
    (case_state_at_acceptance != case_state_at_handoff)
```

Abduction: `accept_handoff` compared the caller-provided `current.state_digest`
with the stored handoff digest, while the caller could provide a stale view.

Deduction: mutate a requirement not included in the transfer, then accept using
the pre-mutation view; the event should say `True`.

Induction: the unfixed regression test failed with
`state_changed_since_handoff=False` while the unrelated requirement was
`BLOCKED`.

Remediation: `record_handoff` now stores a database-derived state fingerprint,
and `accept_handoff` recomputes it inside `BEGIN IMMEDIATE` before changing any
requirement. Old handoffs without this fence are rejected and must be recreated.
The regression test was observed red before the patch and green after it.

### RT-RESOURCE-01 — unbounded counterfactual accumulation

Impact: an authenticated operator could grow per-case counterfactual storage
without bound; every list operation recomputes staleness for every row.

Severity: **low/medium source-confirmed resource risk**. No availability load
test was run against a production-sized database.

Invariant:

```text
counterfactual_rows(case) <= MAX_COUNTERFACTUALS_PER_CASE
```

Remediation: persistence now enforces a limit of 100 rows per case inside the
write transaction, and the API returns `409` rather than silently degrading.
The limit test fills the boundary and asserts the 101st write is rejected.

### RT-DEV-01 — development mutation routes were enabled by default

Impact: if the API was exposed beyond its intended local/demo boundary,
anonymous callers could reach tamper, mandate-revocation, and requirement
mutation simulations.

Severity: **high conditional on network exposure**; demonstrated as a code and
test fact, not as an internet-exposed deployment.

Remediation: `KRAKADYL_ENABLE_DEV_ROUTES` is now opt-in and defaults to off.
Tests that exercise simulations set `KRAKADYL_ENABLE_DEV_ROUTES=1` explicitly.
The remaining deployment requirement is to keep that flag unset outside a
controlled local/demo environment.

## Residual risks after the bearer-authentication round

The previous audit recorded anonymous reads and caller-asserted Level 1/2
identity. The 2026-10-30 authentication round closed those two gaps with
bearer authentication and mandate-principal binding. The remaining risks are:

1. The bearer credentials are shared secrets configured in the process. They
   have no expiry, rotation, MFA, or independent identity-provider lifecycle;
   this is a deployment boundary, not a claim of production authentication.
2. The single SQLite connection and process-local Muse rate limiter need a
   multi-worker/concurrency load test before being claimed safe for deployment.

The first item requires deciding the identity provider, read scopes, token
lifecycle, and frontend session behavior. The current API deliberately fails
closed when no operator verifier is configured.

## Integrated invariant round — authentication before resource lookup

### RT-AUTH-01 — protected POST routes disclosed case existence before auth

**Severity:** Low–medium information disclosure  **Epistemic level:**
**CONFIRMED BY INDUCTION**  **Bucket:** vulnerability

**Invariant:** an unauthenticated request must not learn whether a case exists;
authentication must precede every case lookup on a protected route.

**Abduction:** the read endpoints and `execute` authenticated before checking
the case, but several other protected POST handlers called `_case_or_404`
first. If true, an anonymous request would receive different status codes for
an existing and nonexistent case.

**Deduction:** call `prepare`, `propose_with_muse`, `analyze_note`, and
`recover` directly with no authorization against `case-001` and
`does-not-exist`; predict `(401, 404)` before the fix.

**Induction:** the live code produced `(401, 404)` for all four handlers at
commit `872354a`. After moving `_operator` before `_case_or_404`, the same
experiment produced `(401, 401)` for all four. The regression test is
`tests/test_api.py::test_anonymous_actions_do_not_reveal_case_existence`.

**Causal chain:**

```text
anonymous POST /api/cases/{id}/actions/*
    -> _case_or_404(id)
    -> 404 for unknown id, continue for known id
    -> _operator(authorization)
    -> 401
```

The corrected chain authenticates before resolving the case. The same ordering
was applied to the Level 3 acquisition, Level 4 team/handoff, and Level 5
counterfactual write routes as a variant sweep.

### RT-AUTH-02 — non-principal operators could probe prepared-action IDs

**Severity:** Low information disclosure  **Epistemic level:**
**CONFIRMED BY INDUCTION**  **Bucket:** vulnerability

**Invariant:** an authenticated operator who is not authorized by the case
mandate must not learn whether a pending Level 1/2 action exists.

**Variant query:** the structural endpoint sweep found that `execute` performs
`store.get(prepared_action)` before reloading the mandate and calling
`_authenticated_principal`; the other protected write routes do not have this
same ID-bearing lookup before their authority decision.

**Induction:** on the live code at `21be5cf`, investigator A prepared an action.
Investigator C then called `execute` with the real prepared ID and received
`403` from the mandate check; the same token with
`prepared-does-not-exist` received `404` before the mandate check. The
prediction held exactly. This is distinct from RT-AUTH-01: the caller is
authenticated, but not authorized for the case's mandate.

**Coverage result:** `get_prepared` also exposes prepared-action metadata to any
configured operator by design; the current authorization matrix explicitly
allows authenticated operators to read case metadata. That is a documented
scope assumption, not silently counted as a new bypass. The execution endpoint
is different because it is a consequential action path and should establish
mandate authority before resolving its action identifier.

### RT-AUTH-03 — non-principal operators could persist an unusable acquisition grant

**Severity:** Medium state-integrity / audit pollution  **Epistemic level:**
**CONFIRMED BY INDUCTION**  **Bucket:** vulnerability

**Invariant:** only the principal of the capture mandate may create the durable
human authorization that can enter the acquisition workflow.

**Variant query:** `MandateScopePolicy.authorize` enforces the principal during
`SQLiteAcquisitionGate.create_workflow`, but the API's
`authorize_acquisition` endpoint calls `AcquisitionRuntime.authorize` first.
That method verifies that the bearer token is valid but does not load the live
mandate or apply `MandateScopePolicy`.

**Induction:** with the seeded capture mandate scoped to investigator A, a live
direct API call by investigator C created a proposal and then persisted an
`acquisition_authorization` whose `authorizer_identity` was
`investigator-C`. A later dispatch would be rejected by the scope policy, and
the existing runtime test confirms that rejection; nevertheless the invalid
grant and authorization event already exist in durable state. This is an
authorization decay across the proposal → grant → workflow transition, not a
claim that C can successfully capture evidence.

**Dedupe and fix coverage:** this is not a duplicate of RT-AUTH-01 or
RT-AUTH-02. The earlier fixes cover anonymous lookup ordering and prepared
action execution; neither covers grant issuance. Existing tests cover failed
dispatch, not rejection before durable grant persistence.

### RT-ATOMIC-01 — prepare persistence could commit a partial logical result

**Severity:** Medium state-integrity  **Epistemic level:** **CONFIRMED BY
INDUCTION**  **Bucket:** vulnerability

**Invariant:** persisting a proposal, its decision, and its prepared action is
one logical operation; after a failure, either all required records exist or
none do.

**Abduction:** `_persist_prepare_result` calls `store.put` independently for
`proposed_action`, `decision`, and (when allowed) `prepared_action`. Each
`store.put` commits its own transaction. If the process fails after the first
write, readers can observe a dangling proposal without the decision and action
that define its meaning.

**Deduction:** inject a failure on the second `store.put` during a valid
`prepare`; predict one persisted proposal and zero decision/prepared records.

**Induction:** the live experiment produced exactly that state: the synthetic
failure occurred between writes, `proposed_action` count was `1`, and both
`decision` and `prepared_action` counts were `0`. The helper is shared by
`prepare`, `propose_with_muse`, and `recover`, so the variant surface includes
all three paths.

**Causal chain:**

```text
prepare decision
    -> commit proposed_action
    -> process failure before decision/prepared_action
    -> later reads see a dangling proposal
    -> latest-action lookup cannot reconstruct the decision
```

This is independent of the known HTTP TestClient environment hang and was
confirmed through direct store inspection in a fresh temporary database.

### RT-ATOMIC-02 — acquisition proposal could exist without its audit event

**Severity:** Medium provenance gap  **Epistemic level:** **CONFIRMED BY
INDUCTION**  **Bucket:** vulnerability

**Invariant:** a durable acquisition proposal must be accompanied by its
activity event, or the system must roll back the proposal. The activity feed is
part of the case's reconstruction surface, not optional decoration.

**Variant query:** `propose_acquisition` calls `store.put` for the proposal and
then `store.log_event` in separate commits. The same shape exists for
authorization and some development mutations; proposal creation is the real
acquisition path tested here.

**Induction:** a fresh case accepted a valid proposal, then a synthetic failure
was injected at `store.log_event`. The proposal count was `1` while the event
feed contained only the original `seeded` event. The committed state therefore
claims a proposal exists while its reconstruction log denies that transition.

**Dedupe and coverage:** this is a persistence/provenance variant of
RT-ATOMIC-01, not a duplicate occurrence: RT-ATOMIC-01 leaves a partial action
bundle, while this variant leaves a real acquisition object without its audit
event. The same helper/transaction boundary does not cover either path.

### RT-RESOURCE-01 — Laya note input had no request-size ceiling

**Severity:** Low–medium availability  **Epistemic level:** **CONFIRMED BY
INDUCTION**  **Bucket:** vulnerability

**Invariant:** every untrusted text input sent to an optional local model has a
documented maximum before it reaches model/tokenizer work.

**Abduction:** `AnalyzeNoteRequest.note_text` was a bare `str`, unlike the
bounded capture instructions, SAM prompt, team statement, and handoff note.
The endpoint passes it directly to `analyze_handoff_note`.

**Deduction:** construct an authenticated request with an 8 MiB note and a
recording adapter; predict that the entire string reaches the adapter rather
than being rejected at the API boundary.

**Induction:** the live direct endpoint accepted the payload and the adapter
recorded `8,388,608` bytes. No model call was made in the experiment; the
finding is the missing boundary, not a claim about a particular Laya runtime's
memory multiplier.

**Coverage:** `capture_instructions` is capped at 2,000 characters,
`sam_prompt` at 256, `TeamStatementRequest.statement` at 4,000, and
`HandoffRequest.note` at 4,000. Those sibling paths were not counted as this
finding.

## Refuted vectors

- SQL injection was **FALSIFIED** by tracing the live query sites: external
  values are bound parameters; dynamic SQL is limited to schema-derived table
  names in the new internal fingerprint helper.
- The previously reported observation-ID path traversal was **FALSIFIED** in
  the current code: tamper requires an existing observation ID and the test
  rejects a traversal payload.
- Frontend direct DOM/script injection was **FALSIFIED** by source inspection:
  no `dangerouslySetInnerHTML`, `eval`, or `new Function` sinks were found.
- Counterfactuals changing real case state or becoming executable were
  **FALSIFIED** by the Level 5 tests and the separate append-only storage path.
- Level 3 results promoting themselves without evaluation were **FALSIFIED**
  by the live Meta closing run and its persisted report.

## Completion criterion

The fixed handoff class is complete when the transaction-bound fingerprint is
present on every newly created handoff and all acceptance paths compare the
live database state under the write lock. The authentication residuals are not
complete until caller identity and read access are bound to a real session or
bearer credential on every consequential path.

Skills used: `discriminating-proof`, `invariant-hunting`, `falsifiable-testing`,
`concurrency-reasoning`, `distributed-write-atomicity`,
`resource-exhaustion-review`, `secure-by-construction`, `audit-before-patch`,
`surgical-patcher`, `remediation-driven-reporting`, and `git-discipline`.
