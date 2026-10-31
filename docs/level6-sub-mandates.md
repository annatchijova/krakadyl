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

**Evidence of the invariant, not assertion of it.** `tests/test_delegation.py`
(14 cases) states each property as a falsifiable check: widening any of the
three scope dimensions, starting before the parent, outliving or going
open-ended under a bounded parent, delegating from a revoked or not-yet-effective
parent — each is refused; a narrower slice is granted; the sub binds even where
the parent would allow more; a parent revoked or expired after derivation
revokes the delegated authority at check time. `demo/run_case_003_level6.py`
walks the whole arc end to end, no network, no model.

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

- **No API/persistence wiring for sub-mandates.** This is the deterministic
  core and its composition, with tests and a demo — the same shape every earlier
  level started from (Level 1's "core skeleton" before the workspace, Level 3's
  contracts before the case wiring). Exposing delegation over HTTP, persisting a
  delegation chain, and showing it in the workspace are the next increments.
- **Single-level parent/child only is tested exhaustively.** `derive_sub_mandate`
  composes (a sub-mandate is a `Mandate`, so a sub-sub-mandate is derivable from
  it), and `authority_under_delegation` checks one parent edge; a full chain
  walk that re-checks every ancestor is a documented next step, not a claim made
  here.
- **The other two Level 6 strands — persistent missions across real gaps and
  long-gap re-orientation — are not in this piece.** Missions already persist
  (SQLite) and `next_move`/the shift-handoff already answer "what do I pick up";
  the time-spanning re-orientation that layers on top of them is future Level 6
  work, tracked, not simulated.

## Required closure to call Level 6 complete

Wire delegation through the API and persistence with the same authority
revalidation the capture path already does; walk the full ancestor chain in
`authority_under_delegation` (every ancestor must currently grant, not just the
immediate parent); and add the mission-continuity-across-real-time strand. Until
then this is Level 6's authority core: real, tested, demonstrable, and
architecturally the piece the rest of Level 6 builds on.
