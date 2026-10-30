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

### RT-VERIFY-07 — Responsibility attribution was not bound to the graph

**Observation:** a structured requirement could name `verified_by` as an
identity absent from every `VerificationRecord.verifier_identity`.

**Induction:** the model accepted the mismatch before the fix, allowing the
summary responsibility and the supporting graph to describe different
verifiers. The model now rejects the requirement unless `verified_by` is one of
the structured verifiers.

**Status:** fixed by `28ff6cf`; regression
`test_requirement_verifier_must_be_present_in_structured_records` covers the
negative control. The follow-up regression also requires the identity to be a
root verifier, not merely a parent verifier in the same graph.

### RT-VERIFY-08 — A parent verification could name a missing or changed target

**Observation:** basis observations were checked for presence, digest, and
invalidation, but a parent record's `target_observation_id` was not required to
exist in the current observation set, to still match its custody bytes, or to
keep its logical `Observation.digest` aligned with the custody digest.

**Induction:** a graph containing a parent target that was not present in the
case, whose bytes changed after verification, or whose logical digest diverged
from custody produced no dependency failure before the fix. The validator now
rejects missing, invalidated, or integrity-failed targets for every verification
record, not only the root requirement target; packaging applies the same digest
agreement rule.

**Status:** missing-target validation was fixed by `9156ec2`; target-integrity
revalidation was fixed by `0a65457`; digest agreement in both verification and
packaging was fixed by `a89f709`. Historical target binding was fixed by
`173c75c`; the record now carries the target digest observed at verification
time. Regressions
`test_verification_record_target_must_exist` and
`test_verification_record_target_integrity_is_rechecked` cover target presence
and byte integrity; `test_verification_target_digest_drift_is_rejected`
covers metadata divergence; `test_verification_target_digest_is_bound_at_verification_time`
covers a coherent replacement of both bytes and custody metadata.

### RT-VERIFY-09 — Distinct observation IDs could duplicate one primary source

**Observation:** root independence was compared by `observation_id`, so two
records could use different IDs for observations carrying the same source
identity and still be counted as independent roots.

**Induction:** a duplicate observation with a new ID, the same `source`, the
same digest, and the same underlying file passed the old validator. The
validator now carries source identities through recursive closure and rejects
roots that share one, while retaining the existing ID-level check. Equal
digests from distinct source identities remain a negative control and are
accepted.

**Status:** fixed by `a8e42fa`; regressions
`test_distinct_ids_for_the_same_primary_source_are_not_independent` and
`test_same_digest_from_distinct_primary_sources_can_remain_independent` cover
the adversarial case and its bounded negative control.

### RT-VERIFY-10 — Duplicate observation IDs were resolved by list order

**Observation:** the dependency validator materialized observations as a
dictionary keyed by ID. If the input list contained the same ID twice, the last
entry silently replaced the first one.

**Induction:** an invalidated target followed by a valid observation with the
same ID produced the valid result, while reversing the list changed the
outcome. The boundary now rejects every duplicate observation ID before graph
resolution, including callers handling legacy requirements.

**Status:** fixed by `341a3e0`; regression
`test_duplicate_observation_ids_are_not_last_write_wins` covers the order-
dependence case.

### RT-VERIFY-11 — Duplicate verification IDs could erase graph structure

**Observation:** model construction rejects duplicate `verification_id` values,
but the runtime graph resolver still materialized records as a dictionary. An
unvalidated model copy could therefore replace one record and alter the root
calculation.

**Induction:** two records with one shared ID caused the old resolver to use the
last record and produce no dependency failure, even though the graph was
ambiguous. The runtime validator now rejects duplicate verification IDs before
building `records_by_id`.

**Status:** fixed by `0c62e16`; regression
`test_duplicate_verification_ids_are_not_last_write_wins` covers the bypass of
the construction-time guard.

### RT-VERIFY-12 — A valid graph could verify the wrong requirement target

**Observation:** model construction requires every root record to target the
requirement's `observation_id`, but runtime dependency validation did not repeat
that cross-object binding. A graph for another observation could therefore be
attached to an otherwise resolved requirement through an unvalidated model
copy.

**Induction:** two valid roots for `obs-primary-1` passed while the requirement
governed `obs-target`. The runtime validator now rejects graphs without a root,
graphs without a requirement target, and every root whose target differs from
the requirement target.

**Status:** fixed by `38bcb5e`; regression
`test_verification_roots_must_match_the_requirement_target` covers the
cross-object substitution.

### RT-VERIFY-13 — Runtime accepted non-independent verifier identities

**Observation:** model construction requires distinct `verifier_identity`
values and requires `responsibility.verified_by` to name a root verifier, but
runtime graph validation did not repeat either binding.

**Induction:** an unvalidated model copy with two roots from different sources
but the same verifier, or with `verified_by` set to an unrelated identity,
passed dependency validation. The runtime validator now rejects duplicate
verifier identities and requires the recorded verifier to belong to the root
set.

**Status:** fixed by `9546f35`; regressions
`test_verification_roots_require_distinct_verifiers` and
`test_requirement_verifier_must_be_one_of_the_runtime_roots` cover both
cross-object bindings.

### RT-VERIFY-14 — Runtime allowed target self-reference

**Observation:** the model rejects a record whose basis contains its own target,
but runtime dependency closure treated that target as a valid source when an
unvalidated model copy reached it.

**Induction:** a root could cite its target as its own basis and still pass all
file, digest, and source-independence checks. Closure now rejects the basis
before adding it to the source set.

**Status:** fixed by `6035313`; regression
`test_runtime_rejects_target_as_its_own_verification_source` covers the runtime
bypass.

### RT-VERIFY-15 — Runtime accepted verification records without a basis

**Observation:** `VerificationRecord.basis` has a construction-time minimum
length, but runtime closure simply iterated an empty tuple and accumulated no
sources.

**Induction:** two records with empty bases passed as roots without any primary
evidence. Runtime validation now rejects every record lacking a primary basis
before resolving the graph.

**Status:** fixed by `8f48cc4`; regression
`test_runtime_rejects_verification_records_without_primary_basis` covers the
unvalidated-model bypass.

### RT-VERIFY-16 — Runtime missed cycles across observation targets

**Observation:** runtime detected cycles among `parent_verification_ids`, but
did not traverse the separate dependency graph formed by each record's target
and basis observations.

**Induction:** an acyclic parent graph could still contain
`obs-target -> obs-primary-1 -> obs-target`; the old validator accepted it. A
dedicated observation-dependency DFS now rejects that composition before source
closure is evaluated.

**Status:** fixed by `00ab994`; regression
`test_runtime_rejects_observation_dependency_cycles` covers the cross-layer
cycle.

### RT-VERIFY-17 — Runtime accepted repeated edges inside one record

**Observation:** construction-time validation requires unique basis observation
IDs and unique parent verification IDs, but runtime closure deduplicated or
revisited those edges without reporting the malformed record.

**Induction:** an unvalidated record could cite the same primary observation
twice or list the same parent twice and still pass graph validation. Runtime
now rejects both forms before dependency traversal.

**Status:** fixed by `4ca7378`; regressions
`test_runtime_rejects_duplicate_basis_observations` and
`test_runtime_rejects_duplicate_parent_verification_ids` cover both edge types.

## Negative controls and refuted explanations

- Two structured roots with disjoint valid primary sources remain accepted.
- Two roots sharing direct or recursive primary ancestry are rejected.
- A valid mandate and intact bytes do not override logical invalidation.
- A structured requirement cannot attribute verification to an identity absent
  from its verification records.
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

The focused verification graph suite produced twenty-six passing tests after the
record-uniqueness fix. The full locked suite produced **403 passed**. The live Meta
smoke tests observed parsed Muse output and completed
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
dependency propagation remain open architectural work. Structured
hypothesis-recovery alternatives now require observation/file context and are
revalidated before a suggestion is returned, and hypothesis-review flags use
the same current context. Legacy alternatives and context-free callers still
lack typed dependency closure and remain `WARN`. Structured verification records
created before target-digest binding may deserialize with a missing snapshot,
but validation rejects them until they are rebuilt with the historical target
digest; this is deliberate honest degradation rather than an inferred value.
Source identity is currently the canonical `Observation.source` string; aliases
that refer to one external source under different names remain outside this
check and must be normalized at acquisition.

## Claim audit

| Claim | Layer | Evidence | Status |
|---|---|---|---|
| Direct self-reference was accepted before the patch | Observation | Failing regression `test_verification_cannot_use_target_as_its_own_primary_source` | Confirmed |
| Indirect observation cycles were accepted before the patch | Observation | Failing regression `test_verification_observation_dependencies_cannot_cycle` | Confirmed |
| The current model rejects both classes | Observation | Twenty-six graph tests and full locked suite | Confirmed in tested scope |
| A target could change bytes and digest together after verification | Observation | Failing regression `test_verification_target_digest_is_bound_at_verification_time` | Confirmed and fixed by `173c75c` |
| Distinct IDs could represent one primary source | Observation | Failing regression `test_distinct_ids_for_the_same_primary_source_are_not_independent` | Confirmed and fixed by `a8e42fa` |
| Duplicate IDs could resolve by list order | Observation | Failing regression `test_duplicate_observation_ids_are_not_last_write_wins` | Confirmed and fixed by `341a3e0` |
| Duplicate verification IDs could alter root calculation | Observation | Failing regression `test_duplicate_verification_ids_are_not_last_write_wins` | Confirmed and fixed by `0c62e16` |
| A valid graph could verify the wrong requirement target | Observation | Failing regression `test_verification_roots_must_match_the_requirement_target` | Confirmed and fixed by `38bcb5e` |
| Runtime could accept non-independent verifier identities | Observation | Failing regressions `test_verification_roots_require_distinct_verifiers` and `test_requirement_verifier_must_be_one_of_the_runtime_roots` | Confirmed and fixed by `9546f35` |
| Runtime could accept target self-reference | Observation | Failing regression `test_runtime_rejects_target_as_its_own_verification_source` | Confirmed and fixed by `6035313` |
| Runtime could accept an empty verification basis | Observation | Failing regression `test_runtime_rejects_verification_records_without_primary_basis` | Confirmed and fixed by `8f48cc4` |
| Runtime could accept an observation dependency cycle | Observation | Failing regression `test_runtime_rejects_observation_dependency_cycles` | Confirmed and fixed by `00ab994` |
| Runtime could accept repeated basis or parent edges | Observation | Failing regressions `test_runtime_rejects_duplicate_basis_observations` and `test_runtime_rejects_duplicate_parent_verification_ids` | Confirmed and fixed by `4ca7378` |
| Legacy prose can encode dependencies not recoverable by the graph | Code fact / limitation | `EvidenceRequirement.verified_against` has no typed edges | Open |

## Skills used

`invariant-hunting`, `variant-analysis`, `red-team-auditing`,
`dont-fall-in-love-with-the-bug`, `beyond-the-fix`, `audit-before-patch`,
`falsifiable-testing`, and `daubert-defensible-writing`.
