# Known Limitations

This file is the explicit register of guarantees KRAKADYL does not currently
make. A limitation is not silently converted into a pass: affected paths must
warn, abstain, or remain out of scope until the stated closure condition is met.

## KL-001 — Verification dependency graph is not yet first-class

**Status:** Open architectural limitation.

**Current guarantee:** a prepared action records the full revision of each
`EvidenceRequirement` used for the package. Execution rechecks those revisions,
the mandate, the observation bytes, and the `VERIFIED_DONE` status. A changed
requirement blocks publication.

**Missing guarantee:** the system does not yet represent the complete evidence
verification graph for every case as typed state. Structured
`VerificationRecord`/`VerificationBasis` values now validate direct and
recursive sources, reject shared primary ancestry, and recheck current source
bytes. Structured observations can now be invalidated through an atomic,
audited transition. Legacy requirements still use `verified_against` as
provenance text, and not every external semantic invalidation is forced through
that transition. Therefore the system cannot independently prove that:

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

**Related remediation:** `daa264e` added requirement-dependency snapshots and
execution-time revalidation. That closes case 4, but deliberately does not
claim cases 1–3.

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
