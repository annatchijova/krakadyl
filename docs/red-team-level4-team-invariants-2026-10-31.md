# Red Team — Level 4 Team Authority Invariants (Live) — 2026-10-31

**Method:** Abductive Engineering (A–D–I) + `red-team-auditing`.
**Base:** `main` @ `aa1bc4f`.
**Reproducible evidence:** `tools/redteam_team_probes.py` — boots the real
uvicorn server with three operators and drives the probes over HTTP.
**Outcome:** no new finding. Two Level 4 authority invariants confirmed by
induction on the real request path; the obvious bypasses were attempted and
did not work.

## Scope

Level 4 makes two loud promises about coordination authority: verification must
be independent of the claim, and a conflict is resolved by someone who is not a
party to it. The suite checks these at the function layer; this round confirms
they hold through the real HTTP path, where the team record is written inside
one serialized SQLite transaction (`store.atomic_write`). OS compromise and
direct database editing remain out of scope. The operators A, C, D are all
configured, trusted identities — the question is whether one trusted operator
can escalate past these rules, not whether an outsider can.

## Threat model

- **Attacker CAN:** act as any configured operator; post any team-record kind;
  choose `refers_to`, `expected_requirement_revision`, and timing.
- **Attacker CANNOT:** forge another operator's bearer token; edit the database
  directly; break the atomic team transaction.

## Epistemic legend

CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## Confirmed defenses (induction, live server)

| ID | Probe | Prediction | Observed | Level |
|----|-------|-----------|----------|-------|
| H1 | The claimant (A) verifies its own completion claim | 409 refused | 409, "verification must come from someone other than the claimant" | CONFIRMED BY INDUCTION |
| H1b | A non-claimant (C) verifies A's claim | 200, requirement → VERIFIED_DONE | 200, status `verified_done` | CONFIRMED BY INDUCTION |
| H2 | A party (C) resolves a conflict it is in | 409 refused | 409, "a conflict is resolved by someone who is not a party to it" | CONFIRMED BY INDUCTION |
| H2b | A non-party (D) resolves the conflict | 200 resolved | 200 | CONFIRMED BY INDUCTION |

H1 and H1b together show the rule is a real gate, not a label: the identical
request is refused for the claimant and accepted for an independent operator.
H2/H2b show the same shape for conflict resolution. The causal anchor is
`krakadyl/core/team.py::_transition`: the VERIFIED branch rejects
`record.actor in {claim.actor, reported_done_by}`, and the RESOLUTION branch
rejects `record.actor in conflict.parties` (and, for a DISPUTED conflict, the
requirement's `reported_done_by`/`verified_by` as well).

## Attempted bypasses (FALSIFIED)

Each of these was reasoned through against the code and the live behavior; none
produces an escalation, so no finding is raised.

| Vector | Why it fails |
|--------|--------------|
| Claimant verifies via a **second claimant's** record (A claims, C also claims, A verifies C's record) | The check excludes both `claim.actor` *and* the requirement's `reported_done_by`; the first claimant stays `reported_done_by`, so the original claimant is still refused. |
| **Verify without a claim** (point `refers_to` at a non-completion record) | The VERIFIED branch requires `refers_to[0]` to name a `REPORTED_DONE` record, else `TeamRejected`. |
| **Concurrency TOCTOU** on the independence check (claim and verify raced) | The read of existing records, the independence check, and the append all run inside one `store.atomic_write` transaction; a concurrent write that changed the requirement is caught by the `expected_requirement_revision` optimistic-concurrency gate ("reload before recording"). |
| **Self-resolution via timing** | Same atomic transaction; the party check runs on the freshly read conflict set. |

## Result

No new finding. The Level 4 independence-of-verification and
non-party-resolution invariants hold on the real HTTP path, and the obvious
bypasses are closed by the combination of the explicit actor checks in
`_transition` and the single atomic team-record transaction. This round is
recorded for the adversarial trail — a confirmed defense, earned by induction
and by attempting the bypasses, not asserted.
