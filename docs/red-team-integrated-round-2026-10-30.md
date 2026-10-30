# Integrated Adversarial Review — 2026-10-30

## Scope

This round reviewed the live Level 4 and Level 5 core boundaries after the
previous full audit. The threat model was an authenticated caller or an
internal caller able to provide malformed domain objects to core functions;
operating-system compromise and direct database editing remained out of scope.

The review used `red-team-auditing`, `invariant-hunting`, `variant-analysis`,
`falsifiable-testing`, and `oracle-driven-fuzzing`.

## Invariant under test

```text
Every persisted handoff event must bind its rendered view to the same case
that the transition mutates.
```

The database fingerprint remains the concurrency fence for persisted state. The
additional boundary invariant prevents a foreign `ShiftHandoff` from becoming
the audit metadata of a real case transition.

## Abduction, deduction, induction

### RT-HANDOFF-02 — cross-case view accepted by handoff transitions

**Observation:** `record_handoff` and `accept_handoff` received both a
`case_id` and a caller-provided `ShiftHandoff`, but did not compare the view's
`case_id` with the transition's `case_id`.

**Expected context:** a handoff view is a case-scoped projection. An event for
case A must not carry a view produced for case B, even if the database write is
otherwise fenced.

**Hypothesis:** either handoff transition could persist or consume a foreign
view, creating an audit-integrity fracture without granting authority over the
foreign case.

**Prediction:** construct a valid view, change only its `case_id`, and call each
transition for the original case. The call must reject and must append no event.

**Induction:** both regression tests failed before the patch. The patched code
rejects both calls with `HandoffRejected` before any write.

**Disposition:** confirmed and remediated in commit `73081c3`.

## Added adversarial cases

- A foreign view passed to `accept_handoff` is rejected and leaves the existing
  handoff event list unchanged.
- A foreign view passed to `record_handoff` is rejected and creates no event.
- Existing handoff race, unrelated-state mutation, blocked/unknown transfer,
  reopened requirement, and counterfactual isolation cases remain green.

## Verification

- Targeted core and adversarial suite: **86 passed**.
- Python bytecode compilation: passed.
- `git diff --check`: passed.
- Remote CI run `41130837274` for commit `73081c3`: Python and frontend jobs
  passed.

## Residual questions

- The full HTTP suite is authoritative in CI. Some local `TestClient` runs can
  block in the restricted sandbox; that environmental symptom is not counted
  as a product failure.
- The next useful round is a state-machine sequence generator covering
  acquisition UNKNOWN/reconciliation, team reopen epochs, handoff races, and
  counterfactual persistence in one case lifecycle.
