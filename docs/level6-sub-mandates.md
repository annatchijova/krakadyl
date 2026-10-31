# Level 6 — Sub-mandates (delegation with composition closure)

Level 6 is "investigations that span real time": persistent missions,
sub-mandates, and revisiting a case after a long gap. This document covers the
first core piece built for it — **sub-mandates** — and states precisely what is
and is not implemented, in the same spirit as every earlier level's status.

## Why this is the Level 6 core, not a feature bolted on

A multi-day investigation delegates work. A senior investigator holding broad
authority over a case hands a narrower slice to a junior, or to a sub-task, for
a bounded time. The dangerous failure is a delegation that quietly grants more
than the delegator held, or one that outlives the authority it came from. So
the load-bearing invariant of delegation is **composition closure**: a
sub-mandate can never exceed its parent, and it dies the moment its parent does.
This is invariant 1 (authority decided outside the model, deterministically)
extended to delegation — not a new trust model, the same one composed.

## What is implemented (2026-10-31)

`krakadyl/core/delegation.py`, on immutable `Mandate` snapshots, with
`Mandate.parent_id` naming the parent a sub-mandate was derived from.

**Static closure — enforced at construction (`derive_sub_mandate`).** A
sub-mandate cannot be *built* wider than its parent:

- `resources`, `operations`, and `destinations` are each a subset of the
  parent's; any element the parent does not hold is refused, named explicitly.
- `valid_from` is not before the parent's; `valid_until` is within the parent's
  (and may not be open-ended when the parent is bounded); the window is
  non-empty.
- the parent must itself be valid *now* (not revoked, in effect, not expired) to
  delegate from — authority you do not currently hold cannot be handed out.

Because widening is impossible to construct, no downstream check has to catch
it; a sub-mandate that exists is, by construction, within its parent's static
scope.

**Dynamic closure — enforced at authority time (`authority_under_delegation`).**
A frozen sub-mandate still looks valid on its own after its parent changes, so
the delegated grant is decided against *both* the child and the current parent:
the effective authority for a `(resource, operation, destination)` triple is the
more restrictive of the two, evaluated against the current clock through the one
`check_mandate`. A parent revoked or expired after the child was derived denies
the child too. `parent_id` is a binding, not a grant: a mismatched parent is a
`DelegationRejected`, never a silent allow.

**Full ancestor chain — enforced across every link (`authority_under_chain`).**
Delegation composes: a sub-mandate is a `Mandate`, so a sub-sub-mandate is
derivable from it, and static closure holds transitively (each link is a subset
of its parent, so the leaf is a subset of the root). The dynamic bound is walked
over the whole chain: `authority_under_chain` resolves the leaf-to-root chain
through `parent_id` and requires *every* mandate from the leaf up to the root to
currently grant the triple — the most restrictive wins. Revoking or expiring any
ancestor, however distant, denies the leaf, even when the intermediate mandates
are still fine. A chain with a missing ancestor or a cycle is a
`DelegationRejected`, never a silent allow; the broadest failing authority is
reported first (a revoked root over an out-of-scope leaf reads as the root).

**Wired to the API and persistence.** Delegation is reachable over HTTP, with
the same membership gate the read endpoints use (RT-API-01/02):

- `POST /api/cases/{case_id}/mandates/{parent_id}/delegations` — only the
  parent mandate's principal may delegate (`identity != parent.principal` is
  403); the body's scope is run through `derive_sub_mandate` (a widening or
  out-of-window delegation is 409); the sub-mandate is persisted as an ordinary
  `mandate` object with its `parent_id`.
- `GET /api/cases/{case_id}/delegations` — lists every sub-mandate with its
  resolved chain and whether it is currently live.
- `POST /api/cases/{case_id}/delegations/{sub_id}/authority-check` — decides a
  triple under the sub-mandate against the chain re-resolved from *current*
  persisted mandates, so revoking any ancestor (e.g. through the dev
  revoke-mandate route) flips a previously-granted delegation to denied without
  touching the child. Delegating to someone also makes them a case member
  (`_case_members` now counts every mandate principal), so they can read the
  case and delegate further down.

A delegatee can also **act** under their sub-mandate: `POST .../actions/prepare`
and `POST .../actions/execute` take an optional `sub_mandate_id`. When present,
the caller is authenticated as the sub-mandate's principal and the full chain
must grant the action — at prepare, and again at the execute linearization point
after the one-shot nonce claim, so an ancestor revoked mid-flight denies
dispatch. The prepared action records the mandate it was prepared under
(`mandate_id_checked`), and execute requires the named mandate to match it, so a
sub-prepared action cannot be run under the root (even by the root principal,
who could otherwise re-do it and erase the delegation binding) and cannot be
redirected to a different sub. When `sub_mandate_id` is absent the root path is
byte-for-byte unchanged — the same two `_current_mandate` reads and the same
no-existence-oracle ordering the earlier rounds red-teamed.
`tests/test_api.py::test_sub_mandate_delegation_over_http` and
`::test_execute_under_a_delegated_sub_mandate` exercise the whole HTTP flow,
including revoke-kills-the-delegation at prepare and the binding checks.

**Evidence of the invariant, not assertion of it.** `tests/test_delegation.py`
(21 cases) states each property as a falsifiable check: widening any of the
three scope dimensions, starting before the parent, outliving or going
open-ended under a bounded parent, delegating from a revoked or not-yet-effective
parent — each is refused; a narrower slice is granted; the sub binds even where
the parent would allow more; a parent revoked or expired after derivation
revokes the delegated authority at check time. For a three-level chain
(root → lead → junior) the same holds transitively: the leaf binds below the
root, revoking the distant root or an intermediate ancestor denies the leaf,
root expiry expires the whole chain, and a broken or cyclic chain is rejected.
`demo/run_case_003_level6.py` walks the whole arc end to end, no network, no
model.

## Invariants carried from Level 1 (not deferred)

- **Authority outside the model (1):** a delegation is a typed authority
  construct decided by `check_mandate`; no model output is involved.
- **Evidence vs authority separate (3):** delegation changes only the authority
  dimension; evidence state is untouched.
- **Responsibility explicit (4):** a sub-mandate names its own `principal` (the
  sub-investigator) and its `parent_id`; who delegated what to whom is recorded,
  never assumed.
- **Untrusted content isolation (6):** a sub-mandate is built from immutable
  `Mandate` snapshots, never from investigated content or model output.

Determinism holds: no float, no mutation (both mandates are frozen), and the
one `check_mandate` is reused rather than re-deriving scope logic.

## What is deliberately not built yet (stated, not approximated)

- **No delegation workspace UI yet.** Delegation is fully usable over the API
  (create, list, authority-check, and prepare/execute *under* a sub-mandate —
  see "Wired to the API" below), but the React workspace does not yet show a
  case's delegation tree or let an investigator delegate from it. That view is
  the remaining Level 6 interface work.
- **The other two Level 6 strands — persistent missions across real gaps and
  long-gap re-orientation — are not in this piece.** Missions already persist
  (SQLite) and `next_move`/the shift-handoff already answer "what do I pick up";
  the time-spanning re-orientation that layers on top of them is future Level 6
  work, tracked, not simulated.

## Required closure to call Level 6 complete

Add the delegation workspace UI (show a case's delegation tree and let an
investigator delegate and act from it), and add the
mission-continuity-across-real-time strand. The authority core, the full
ancestor-chain walk, the HTTP/persistence wiring, and execution *under* a
sub-mandate are built; what remains is the interface and the time-spanning
strand. This is Level 6's authority mechanism end to end — a delegatee can be
given a strictly bounded slice, act within it, and lose it the instant any
ancestor is revoked — real, tested, demonstrable over HTTP, and the piece the
rest of Level 6 builds on.
