# Composed Authorization Review — 2026-10-30

## Scope and threat model

This round attacks the interaction between Muse proposals, Laya signals,
mandates, evidence requirements, shared-custody conflicts, execution, and
receipts. The attacker may supply model-facing text and may cause a valid
caller to select an available core entry point. The attacker cannot modify
source code, stored bytes, mandate records, or the deterministic engine.

The target invariant is:

```text
authority(executed_effect) <= authority(granted_by_the_full_case_state)
```

In particular, a convenience path must transport every authority-relevant
fact that the full API path uses. A valid mandate plus authentic bytes plus a
valid individual action is not enough if an open team conflict or an
acquisition-route constraint disappears between components.

Skills used: `agent-trust-boundaries`, `authorization-surface-mapping`,
`llm-out-of-the-loop`, `red-team-auditing`, `invariant-hunting`, and
`variant-analysis`.

## Finding

### RT-COMPOSE-01 — convenience execution path dropped Level 4/3 context

**Bucket:** software vulnerability in the core composition contract.

**Prior observation:** the HTTP prepare/Muse paths passed
`conflicted_requirement_ids` and `resolvable_requirement_ids` to the policy
engine. `assemble_evidence_package`, another package-and-receipt sink, did not
accept or forward those facts.

**Abduction:** a caller using the convenience wrapper could reach a different
policy result from the API for the same mandate, observations, and
requirements, because shared-custody conflicts were absent from the wrapper's
evidence check.

**Deduction:** pass an open conflict for a verified requirement to the wrapper.
The expected result is `FORBIDDEN`, no package directory, and a non-executed
receipt.

**Induction:** the regression test initially failed because the wrapper had no
such parameter. After the patch, the same test passed with `FORBIDDEN` and no
published package. The composed Laya/Muse case also passed: high Laya
verification signals and a valid Muse export candidate did not turn
`REPORTED_DONE` evidence into execution.

**Remediation:** the wrapper now transports both Level 3 route context and
Level 4 conflict context into preparation and execution. The contract is
documented in `krakadyl/core/executor.py`.

## Composed cases added

- Open shared-custody conflict through the package-and-receipt wrapper.
- Laya says the note strongly claims verification; Muse proposes an apparently
  valid export; the evidence remains only `REPORTED_DONE`.
- Muse candidates with out-of-scope resources, destinations, or operations are
  denied by the deterministic engine.
- Muse reasoning containing an instruction to ignore policy does not alter an
  otherwise valid deterministic verdict.

## Discarded vectors

| Vector | Result | Reason |
|---|---|---|
| Laya signal directly resolves a requirement | FALSIFIED | Laya output is not read by core transitions; the composed test leaves the requirement unverified. |
| Muse reasoning widens mandate scope | FALSIFIED | `reasoning` is display text; structured fields still pass through mandate checks. |
| Authentic bytes alone authorize export | FALSIFIED | `check_evidence` requires an independently verified requirement. |

## Verification

- New composition and wrapper tests passed.
- Existing executor, handoff, counterfactual, and Muse adversarial tests remain
  part of the regression run.
- Full CI is required before treating the patch as integrated across the HTTP
  surface.

## Residual boundary

The standalone receipt verifier proves canonical seal and chain linkage. It
does not independently derive mandate authority from the receipt alone; a
consumer must verify the linked action and decision records as well. That is a
provenance boundary to preserve in future export formats, not a claim that the
current receipt hash is broken.
