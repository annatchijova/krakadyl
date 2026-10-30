# Full Red-Team Audit — 2026-10-30

## Scope and epistemic discipline

This audit covers the live `main` tree at commit `a80e10e` after the ordered
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
  `tests/test_laya_adapter.py` excluded. The external CI run
  `41127587728` on `a80e10e` passed the complete configured Python command,
  including the HTTP suite, and the frontend build/lint jobs.
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

### RT-ATOMIC-03 — prepared action state could commit without its activity event

**Severity:** Medium provenance gap  **Epistemic level:** **CONFIRMED BY
INDUCTION**  **Bucket:** vulnerability

**Invariant:** a prepared result that can later be retrieved or executed must
be committed together with the activity event that explains its creation. A
failure writing that event must roll back the proposal, decision, and prepared
action as one logical transition.

**Firstness:** `_persist_prepare_result` committed the three result objects,
then each API route called `store.log_event` in a separate transaction. The
same split existed in the Muse and recovered-action paths.

**Abduction:** an event-store failure after the result commit would leave an
action available through the prepared-action endpoint without a corresponding
activity record.

**Deduction:** install a SQLite trigger that aborts `prepared` event inserts,
invoke the real HTTP prepare function, and inspect all three object kinds. The
unfixed path should raise while leaving the result objects; the corrected path
should raise with all three absent.

**Induction:** the unfixed regression test observed one persisted proposal,
decision, and prepared action after the injected event failure. After the
patch the same test passed with all three rolled back. The regular prepare,
Muse, recovery, store rollback, and execution tests remained green.

**Remediation:** `put_prepare_result_and_log_event` now writes the complete
result bundle and its event under one `BEGIN IMMEDIATE` transaction. Prepare
and Muse use it for every result; recovery uses it when it creates a prepared
route and retains a separate event-only transaction when it merely closes
without one.

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

### RT-AUTH-04 — execution reused a pre-claim mandate snapshot

**Severity:** High conditional authorization race  **Epistemic level:**
**CONFIRMED BY INDUCTION**  **Bucket:** vulnerability

**Invariant:** the mandate used by the executor must be the mandate observed
after the one-shot execution claim and immediately before dispatch. A mandate
revoked before that point must prevent publication, even when the prepared
action, evidence bytes, and original authorization remain intact.

**Firstness:** the API loaded the mandate once for initial principal
authentication, then loaded the prepared action, evidence, and nonce and passed
the original object to `execute_prepared_action`. The core revalidated the
object it received, but the API did not reload the current stored mandate at
the effect boundary.

**Abduction:** a revocation committed between the initial authentication read
and dispatch would be invisible to the executor because the caller supplied a
stale snapshot.

**Deduction:** force `_current_mandate` to return the original mandate on the
first read and a revoked, higher-revision mandate on the next read. The
unfixed endpoint should execute with one read; the corrected endpoint should
make two reads and return a non-executed receipt containing the revocation
reason.

**Induction:** the regression test first failed on the unfixed code: it returned
`200` with an executed receipt and only one mandate read. After the surgical
patch, the same test passed with two reads and `receipt.executed == false`.
The related happy-path, replay, nonce-burn, and concurrent-claim tests also
passed.

**Remediation:** `execute` now reloads the mandate and rebinds the authenticated
principal after claiming the nonce, then passes that exact snapshot to the
executor. This read is the authorization linearization point for dispatch. A
revocation observed there blocks publication; the already-claimed nonce remains
consumed, conservatively preventing an ambiguous retry from bypassing the
authorization transition.

**Residual boundary:** a revocation committed after this linearization read
cannot recall a dispatch already authorized by the API. Stronger recall would
require a transactional effect boundary or a downstream capability that checks
a fencing revision at the irreversible sink.

### RT-AUTH-05 — stale acquisition proposals could receive durable grants

**Severity:** Medium authorization-state integrity  **Epistemic level:**
**CONFIRMED BY INDUCTION**  **Bucket:** vulnerability

**Invariant:** an acquisition authorization may be issued only when the
proposal's mandate identity, revision, validity window, and capture scope still
match the current mandate. A grant for a stale proposal must not be persisted.

**Firstness:** `authorize_acquisition` checked that the bearer identity matched
the current capture principal, then called the runtime grant issuer using the
stored proposal. The issuer bound the old proposal revision into the grant but
did not load the current mandate; the durable grant was written before the
dispatch gate could reject it.

**Abduction:** revoking or revising the capture mandate after proposal creation
would leave a durable authorization that could never create a valid workflow.

**Deduction:** create a valid proposal, replace the capture mandate with a
higher-revision revoked mandate, then authorize the old proposal. The unfixed
endpoint should return success and store an authorization; the corrected
endpoint should return `409` and leave the authorization collection empty.

**Induction:** the regression test observed the unfixed `200` response and a
persisted authorization. After the patch it returned `409`, naming the mandate
state, and persisted no grant. The non-principal, full lifecycle, and
non-principal capture tests remained green.

**Remediation:** the API now reloads the capture mandate after resolving the
proposal, rebinds the authenticated identity, checks proposal mandate ID and
revision, and runs the same capture scope/validity check before issuing the
grant. It repeats that validation after grant construction and before the
atomic object/event write, so a mandate change observed in that window leaves
no grant behind. The atomic dispatch gate remains the final fence for a
concurrent change after persistence; it still checks the current mandate before
any source or processor call.

**Residual boundary:** the API-level precheck is not itself the durable
linearization point. The system's safety claim depends on the gate's atomic
compare-and-consume operation at capture dispatch, while the precheck prevents
known-stale grants from polluting durable state.

### RT-RECEIPT-01 — API execution did not extend the receipt chain

**Severity:** Medium audit-integrity gap  **Epistemic level:** **CONFIRMED BY
INDUCTION**  **Bucket:** vulnerability, partially remediated

**Invariant:** consecutive API executions for one case must link each receipt
to the previous persisted receipt, while concurrent successors must not silently
fork the chain.

**Induction:** two sequential HTTP executions initially produced a second
receipt with `prev_hash == None` despite the first receipt having a valid hash.
After the integration patch, the sequential regression passed and the second
receipt linked to the first. A forced interleaving of two distinct executions
then showed that both can still read the same old head and produce divergent
successors.

**Remediation:** `execute` now reads the current case receipt head and passes it
to `execute_prepared_action`; sequential API receipts are chained. The
concurrent variant remains an explicit limitation in `known-limitations.md`
(`KL-005`). No process-wide lock was added around package assembly because the
critical section includes filesystem I/O and would turn external work into a
throughput and liveness hazard.

**Required closure:** implement a durable receipt-position reservation or
compare-and-swap append protocol with recovery for abandoned positions. Until
then, the API's receipt chain is trustworthy for serialized execution only.

## Remediation status

The findings in this integrated round were repaired after the induction probes:

- **RT-AUTH-02:** `execute` now authenticates the mandate principal before
  resolving `prepared_action_id`; the valid and nonexistent ID probes both
  return `403` to the wrong operator.
- **RT-AUTH-03:** acquisition authorization now checks the live capture
  mandate principal before creating a durable grant; the rejected operator
  leaves zero authorization records.
- **RT-ATOMIC-01:** prepare, Muse, and recovery results use one SQLite
  transaction for proposal, decision, and prepared action.
- **RT-ATOMIC-02:** acquisition proposal and authorization objects are written
  atomically with their activity events.
- **RT-RESOURCE-01:** Laya notes are bounded to 4,000 characters at the
  Pydantic boundary, with a 4,001-character regression test.
- **RT-AUTH-04:** execution reloads and reauthenticates the mandate after the
  nonce claim, before passing the snapshot to the executor.
- **RT-AUTH-05:** acquisition authorization rejects mandate-revision, validity,
  and scope changes before persisting a grant; capture retains its atomic final
  gate.
- **RT-ATOMIC-03:** prepared result bundles and their activity events now share
  one transaction across prepare, Muse, and recovery creation paths.
- **RT-RECEIPT-01:** sequential API receipt chaining is fixed; concurrent chain
  append remains tracked as KL-005 rather than being presented as closed.

The store rollback tests, acquisition/core tests, compile check, frontend build,
and lint pass. The local sandbox still has an AnyIO worker-thread limitation,
but CI run `41127587728` is the authoritative external verification and passed
the HTTP regression suite. CI reported only the existing React lint warning and
the runner's Node 20 action deprecation annotation.

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
`surgical-patcher`, `remediation-driven-reporting`,
`dont-fall-in-love-with-the-bug`, and `git-discipline`.
