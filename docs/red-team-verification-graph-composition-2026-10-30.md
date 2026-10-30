# Red-Team Review — Verification Graph Composition — 2026-10-30

## Scope and method

This review started from the invariant that a consequential action may rely only
on evidence whose verification basis is valid, independent, and still valid at
the point of use. The review followed the repository's abductive loop:

1. observe the current model and every consumer of verification state;
2. derive a falsifiable bypass for each neighboring composition;
3. run a regression against the live code before changing it;
4. re-run the original case, the negative control, and the full suite.

The test corpus is the structured verification graph suite, the API suite, the
composed-authorization tests, and the full locked-environment suite. This is an
authorized review of the local repository. It does not claim coverage of
unrepresented external adjudication systems or every possible semantic source
invalidation.

## Invariant

For every verification graph used by an action:

```text
the verification basis is not the target itself,
the observation-dependency graph is acyclic,
independent roots do not share primary ancestry,
all referenced observations remain present, valid, and byte-integral,
and every consumer describes the same current state as the execution gate.
```

The invariant is enforced at different layers: Pydantic construction rejects
malformed graph structure; `validate_verification_dependencies()` rechecks
current observations and files; `check_evidence()` feeds both preparation and
execution; `_currently_verified()` keeps the API overview and Muse summary from
describing stale evidence as verified.

## Findings and remediation

### RT-VERIFY-01 — Prepared verification state was not snapshotted

**Observation:** before the revision fence, execution rechecked the mandate,
file digest, and `VERIFIED_DONE`, but not the complete requirement used during
preparation.

**Induction:** changing only the verification provenance after preparation
allowed publication before the fix. After the fix, execution returns a
non-executed receipt and publishes no manifest.

**Status:** fixed by `daa264e`; retained as a regression and documented in
`red-team-verification-invalidation-2026-10-30.md`.

### RT-VERIFY-02 — Logical invalidation of the target bypassed legacy evidence checks

**Observation:** a target `Observation` marked `invalidated=True` could still
pass a legacy requirement with `VERIFIED_DONE` when the file bytes were intact.

**Induction:** the adversarial regression published before the fix. The current
`check_evidence()` derives `CONFLICTING` from logical invalidation before
preparation or execution can publish.

**Status:** fixed by `aafcb5f`. The invalidation transition itself is atomic and
audited by `665e965` and its preceding commits.

### RT-VERIFY-03 — Duplicate requirements used last-write-wins semantics

**Observation:** two distinct requirements could govern one observation. The
mapping used by the executor retained whichever requirement appeared last.

**Induction:** placing an unverified requirement first and a verified one last
produced `ALLOWED`. The current derivation records the duplicate as an evidence
conflict and refuses both normal and route-based resolution.

**Status:** fixed by `1f0fb87`.

### RT-VERIFY-04 — A verification could use its target as its own source

**Observation:** structured records checked verifier identity and source digest,
but did not forbid a record from naming its target observation as its primary
basis.

**Induction:** a self-referential record was accepted before the fix. The model
now rejects it with `target observation cannot be a verification source`.

**Status:** fixed by `28bdf63`.

### RT-VERIFY-05 — The observation dependency graph could cycle indirectly

**Observation:** the record-parent graph was acyclic, but observation edges were
not checked. A record could verify A using B while another record verified B
using A.

**Induction:** the cyclic graph was accepted before the fix even though its
record graph had no parent cycle. The model now rejects cycles in both graphs.

**Status:** fixed by `8a2cbbe`.

### RT-VERIFY-06 — A stale consumer described invalid evidence as verified

**Observation:** execution and the case overview had current-state checks, but
`_case_summaries()` still used only the historical requirement status when
building Muse's read-only context.

**Inference:** this did not grant authority, because Muse remains outside the
decision path, but it violated the consistency invariant and could cause a
misleading proposal.

**Status:** fixed by `fd7d389`. The overview and Muse summary now share
`_currently_verified()`.

## Negative controls and refuted explanations

- Two structured roots with disjoint valid primary sources remain accepted.
- Two roots sharing direct or recursive primary ancestry are rejected.
- A valid mandate and intact bytes do not override logical invalidation.
- A changed requirement revision does not remain executable after preparation.
- Muse output still cannot grant authority or resolve evidence; the live
  adversarial and composed-authorization tests preserve this boundary.
- The reported API hang was not a product authorization defect. It reproduced
  intermittently only in the globally installed dependency set, whose FastAPI
  and Starlette versions differed from `uv.lock`. The locked environment passed
  the reproduction and the full suite.

## Verification record

The locked environment produced:

```text
382 passed in 13.67s
```

The focused verification graph suite produced eight passing tests after the
cycle fix. The live Meta smoke tests observed parsed Muse output and completed
SAM sidecar attempts, including an empty candidate that remained unevaluated.
Those live calls establish behavior for the bounded run only; they do not
establish robustness against provider drift.

## Remaining limitation

The typed graph governs requirements that carry `VerificationRecord` values.
Legacy requirements still carry prose such as `verified_against`; the system
cannot reconstruct an unrecorded external semantic dependency from that prose.
Every provider or human source invalidation must therefore enter the typed,
atomic invalidation transition, or the safe claim is abstention rather than
automatic propagation. Migration of legacy provenance and first-class
dependency propagation remain open architectural work. A separate planning
limit remains: hypothesis-recovery suggestions do not currently receive
observation/file context, so they must be treated as `WARN` until the normal
evidence gate revalidates them.

## Claim audit

| Claim | Layer | Evidence | Status |
|---|---|---|---|
| Direct self-reference was accepted before the patch | Observation | Failing regression `test_verification_cannot_use_target_as_its_own_primary_source` | Confirmed |
| Indirect observation cycles were accepted before the patch | Observation | Failing regression `test_verification_observation_dependencies_cannot_cycle` | Confirmed |
| The current model rejects both classes | Observation | Eight graph tests and full locked suite | Confirmed in tested scope |
| Legacy prose can encode dependencies not recoverable by the graph | Code fact / limitation | `EvidenceRequirement.verified_against` has no typed edges | Open |

## Skills used

`invariant-hunting`, `variant-analysis`, `red-team-auditing`,
`dont-fall-in-love-with-the-bug`, `beyond-the-fix`, `audit-before-patch`,
`falsifiable-testing`, and `daubert-defensible-writing`.
