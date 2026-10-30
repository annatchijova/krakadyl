# Verification Dependency Invalidation Review — 2026-10-30

## Invariant

```text
The independent verification basis used at prepare time must still be the
same valid basis at execution time.
```

Authentic bytes, a current mandate, and a surviving `VERIFIED_DONE` label are
not sufficient if the verification dependency changed in between.

## Threat model

The caller can prepare an action, then the case state can legitimately change
before execution. The caller cannot modify code or bypass the deterministic
executor. The scenario is not malicious file tampering: the file remains byte-
for-byte authentic, while the recorded basis for independent verification is
invalidated by a later case update.

## RT-VERIFY-01 — verification basis was not part of the execution snapshot

**Epistemic level:** CONFIRMED BY INDUCTION.

**Observation:** before the patch, `execute_prepared_action` rechecked the
mandate, file digest, and `VERIFIED_DONE` status, but did not compare the full
`EvidenceRequirement` revision used at preparation.

**Prediction:** prepare an allowed export, change only `responsibility.verified_against`
to record that the common primary source was invalidated, keep the mandate and
file unchanged, and execute. The vulnerable path would publish the package;
the required behavior is a non-executed receipt.

**Induction:** the regression first executed successfully, proving the gap.
After the fix it returns a non-executed receipt with:

```text
verification dependency for obs-a1 changed since this action was prepared
```

No manifest or package directory is published. The mandate and file digest are
unchanged in the test.

## Remediation

`PreparedAction` now stores sorted `(observation_id, requirement_id, full
requirement revision)` bindings. Execution reconstructs the current bindings
and refuses to publish if any binding is missing, substituted, or changed.
Prepared actions without this snapshot are rejected and must be recreated.

## Verification

- The new transition regression and related invalidation/executor/recovery
  tests pass.
- Integrated focused suite: **69 passed**.
- The full CI run is the final check for persisted prepared-action compatibility
  and HTTP serialization.

## Residual boundary

The current domain model records `verified_against` as provenance text and does
not yet model a multi-verifier dependency graph or a first-class primary-source
object. Therefore this fix detects invalidation when the case transition
updates the `EvidenceRequirement` revision. A future source invalidation path
must update that requirement atomically; otherwise no downstream component can
know that an external source became invalid.

Skills used: `invariant-hunting`, `red-team-auditing`, `variant-analysis`,
`atomic-state-mutation`, `falsifiable-testing`, and `audit-before-patch`.
