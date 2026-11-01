# Red Team — Level 6 Delegation & Mission Continuity (Live) — 2026-11-01

**Method:** Abductive Engineering (A–D–I) + `red-team-auditing` +
`destination-driven-construction`'s per-level review (does this level hold, and
does it preserve the invariants of the levels before it?).
**Base:** `main` @ `bad1b41`.
**Reproducible evidence:** `tools/redteam_level6_probes.py` (live server).
**Outcome:** no new finding. Level 6's delegation authority holds under
adversarial use, and the earlier rounds' invariants survive the new code.

## Scope

Level 6 added sub-mandate delegation (create / list / authority-check / prepare
and execute *under* a sub-mandate) and mission continuity across a real-time gap
(`resume_after_gap`, `GET /resume`). This round attacks the delegation authority
as it runs and checks that threading `sub_mandate_id` through prepare/execute did
not weaken the root path the previous rounds red-teamed.

## Threat model

- **Attacker CAN:** act as any configured operator; delegate; prepare and
  execute under a sub-mandate; revoke a mandate (dev route stands in for any
  revocation path); choose request fields.
- **Attacker CANNOT:** forge another operator's token; construct a mandate
  except through `derive_sub_mandate` (the only sub-creation path); edit the
  database.
- **Invariant under test:** a delegatee's authority never exceeds its chain and
  is lost the instant any ancestor is revoked or expires — including between
  prepare and execute.

## Epistemic legend

CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## Confirmed defenses (induction, live server)

| ID | Probe | Prediction | Observed | Level |
|----|-------|-----------|----------|-------|
| RT-L6-1 | A delegatee prepares an action outside its slice (device-B, held by the parent, not the sub) | 409 | 409 | CONFIRMED BY INDUCTION |
| RT-L6-3 | A sub-sub delegated from the sub tries to widen back to device-B | 409 | 409 | CONFIRMED BY INDUCTION |
| RT-L6-2 | The parent is revoked between the delegatee's prepare and execute | 409 at execute | 409, "delegated authority no longer covers this action: root mandate …" | CONFIRMED BY INDUCTION |

RT-L6-1 confirms the chain gate binds a prepare to the *sub's* scope, not the
broader parent's — the sub is the limit even where the parent would allow more.
RT-L6-3 confirms static closure composes transitively: a sub-sub cannot recover
scope the sub gave up, because `derive_sub_mandate` checks each link against its
immediate parent. RT-L6-2 is the sharpest: it confirms the execute-time chain
re-check at the linearization point (after the one-shot nonce claim) catches an
ancestor revoked *mid-flight*, so a delegated action in progress dies with its
chain rather than completing on a now-withdrawn authority.

## Attempted bypasses (FALSIFIED / confirmed-safe)

| Vector | Why it fails |
|--------|--------------|
| Execute a sub-prepared action under the root (root principal re-running it) | `prepared.mandate_id_checked` must equal the declared mandate; a root execute of a sub-prepared action is 409 |
| Execute a sub-prepared action by naming a *different* sub the attacker controls | same binding check (declared must equal `mandate_id_checked`) plus authentication as that sub's principal |
| Construct a sub-mandate wider than its parent, or with a forged `parent_id` | the only sub-creation path is `derive_sub_mandate`, which sets `parent_id` to the real parent and refuses any widening; `authority_under_chain` resolves ancestors from the store, not from caller input |
| Spoof the resume gap to hide a change | `GET /resume` derives `since` from the last recorded event, never from caller input; it is a read and logs no event |
| A delegated principal reading a case they are not on | delegating makes them a mandate principal, which `_case_members` counts — so reading is intended once they hold authority, and refused before |

## Preservation of prior invariants

`destination-driven-construction` requires checking the new level did not break
earlier ones. The root prepare/execute path is byte-for-byte unchanged when
`sub_mandate_id` is absent — the same two `_current_mandate` reads
(mandate-reload-before-dispatch, d906a23), the same authorize-before-lookup order
(no prepared-id existence oracle), and the same receipt-chain append (RT-CHAIN-01
/02) and nonce replay control. The full suite — which still carries every earlier
regression test, including those three that the first threading attempt tripped
and this version restores — passes at 456. RT-API-01/02 membership gating extends
to the new delegation and resume endpoints.

## Result

No new finding. Level 6's delegation holds under adversarial use — the chain
binds a delegatee below its slice, transitive closure is intact, and an ancestor
revoked mid-flight denies dispatch — and the earlier authority, receipt-chain,
and read-authorization invariants are preserved. Recorded for the adversarial
trail: a confirmed defense earned by induction and by attempting the bypasses.
