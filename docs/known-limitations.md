# Known Limitations

This file is the explicit register of guarantees KRAKADYL does not currently
make. A limitation is not silently converted into a pass: affected paths must
warn, abstain, or remain out of scope until the stated closure condition is met.

The complete adversarial review of verification-graph composition is recorded
in [`red-team-verification-graph-composition-2026-10-30.md`](red-team-verification-graph-composition-2026-10-30.md).

## KL-001 — Verification dependency graph is not yet first-class

**Status:** Open architectural limitation.

**Current guarantee:** a prepared action records the full revision of each
`EvidenceRequirement` used for the package. Execution rechecks those revisions,
the mandate, the observation bytes, and the `VERIFIED_DONE` status. A changed
requirement blocks publication.

**Missing guarantee:** the system does not yet represent the complete evidence
verification graph for every case as typed state. Structured
`VerificationRecord`/`VerificationBasis` values now validate direct and
recursive sources, reject shared primary ancestry, self-reference, and cycles
in the observation dependency graph, and recheck current source bytes.
Duplicate requirements for one observation are treated as a conflict rather
than last-write-wins. Structured observations can now be invalidated through an
atomic, audited transition, and the executor, case overview, and Muse summary
use current validity checks. Legacy requirements still use `verified_against`
as provenance text, and not every external semantic invalidation is forced
through that transition. Therefore the system cannot independently prove that:

- every legacy primary source used by a verification is still valid when
  execution happens if the source changed without a corresponding requirement
  update;
- an external semantic invalidation event propagates automatically from a
  source node through all dependent verifications and requirements.

**Impact:** a source can become semantically invalid while the derived
`EvidenceRequirement` bytes remain unchanged if the invalidation happens
outside the typed observation transition. The current revision fence and byte
checks cannot detect a change that no represented state records. This is not a
claim that the receipt seal is broken; it is a boundary of the evidence model
before sealing.

**Required closure:** route every source invalidation, including provider and
human adjudication paths, through the typed atomic transition. Atomically mark
dependent verifications and requirements stale or make execution abstain until
reevaluation. Migrate legacy requirements away from prose-only provenance.

**Adversarial acceptance cases:**

1. Two investigators verify a target using the same primary source; the graph
   rejects the pair as not independently corroborating. **Implemented for
   structured direct and recursive sources.**
2. Two investigators verify a target using disjoint valid primary sources; the
   graph accepts the independence claim. **Implemented for structured direct
   and recursive sources.**
3. Prepare with valid sources, invalidate one primary source without editing the
   derived requirement, then execute; publication is refused. **Implemented for
   structured sources, including typed logical invalidation.**
4. Change only a derived requirement; the existing revision fence still refuses
   execution. **Implemented.**
5. A verification uses its target as a source, directly or through a cycle of
   observation dependencies. **Implemented.**
6. A stale consumer describes invalidated structured evidence as verified.
   **Implemented for the executor, case overview, and Muse summary.**

**Related remediation:** `daa264e` added requirement-dependency snapshots and
execution-time revalidation. `28bdf63` and `8a2cbbe` close direct and indirect
self-reference for structured graphs; `fd7d389` aligns read-only summaries
with current evidence validity. These fixes do not migrate legacy prose into a
typed dependency graph.

## KL-002 — Standalone receipt verification does not derive authority

**Status:** Open export-boundary limitation.

The stdlib receipt verifier proves canonical sealing and chain linkage. It does
not, from a receipt alone, reconstruct the mandate scope, evidence graph, or
independent verification basis. An exported receipt must therefore be consumed
with its linked action, decision, case-state snapshot, and evidence provenance.

**Required closure:** define a versioned evidence-authority envelope whose
sealed payload includes or cryptographically binds the complete authorization
and verification-graph closure needed by an offline verifier.

## KL-003 — External provider/model behavior is not a correctness guarantee

**Status:** Open model-quality limitation; authority remains deterministic.

Muse, Laya, and SAM can produce useful or wrong proposals/signals/annotations.
Their outputs cannot grant authority, resolve evidence, or execute actions.
Live probes demonstrate observed behavior for a bounded corpus only; they do not
establish robustness against model drift or every adversarial input.

## KL-004 — Legacy hypothesis planning lacks typed observation context

**Status:** Partially closed for structured requirements; legacy planning
remains limited. This is not an execution authorization bypass.

`propose_hypothesis_recovery()` receives requirements and hypotheses. For a
structured alternative it now requires the current observation collection and
artifact paths, walks the verification graph, and abstains when context is
missing or a dependency is invalid. The case overview's hypothesis review
detector also receives current context and flags invalidated structured
evidence, and the API handoff view supplies the same context. Legacy
alternatives and pure callers without typed context still use historical
requirement state because prose provenance has no typed edges. The execution
path remains protected because a recovered action must pass
`check_evidence()` and the normal prepare/execute gates.

**Impact:** a legacy source requirement whose external semantic status changed
outside the typed observation transition can still influence a recovery
suggestion or planning view. Neither output is permission, evidence resolution,
or publication, but it should be displayed as `WARN`.

**Required closure:** migrate legacy provenance to typed dependency records and
make all callers provide current observation and custody context.

## KL-005 — Concurrent API executions need a durable receipt append protocol

**Status:** Open concurrency limitation.

The API now links sequential execution receipts by passing the latest persisted
receipt hash into the deterministic executor. Two distinct executions that
start concurrently can still read the same chain head before either receipt is
stored, producing two valid but divergent successor hashes. The action nonce
prevents replay of one prepared action; it does not serialize different
prepared actions or establish a receipt-chain lease.

This is not currently a decision-authority bypass: each action still passes the
mandate/evidence gates, and each receipt seals its own payload. It is an audit
integrity limitation for multi-worker or multi-process execution.

**Required closure:** reserve a chain position durably before or while
persisting the receipt, with compare-and-swap/lease recovery semantics that do
not hold a database or process lock across package assembly or other I/O. The
receipt hash must be recomputed from the reserved predecessor and the verifier
must reject abandoned or duplicated positions.
