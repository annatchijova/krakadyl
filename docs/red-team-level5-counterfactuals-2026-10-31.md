# Red Team — Level 5 Comparable Routes (Live) — 2026-10-31

**Method:** Abductive Engineering (A–D–I) + `red-team-auditing` + `beyond-the-fix`.
**Base:** `main` @ `87416a5`.
**Reproducible evidence:** `tools/redteam_level5_probes.py` (live server) and
`tests/test_api.py::test_case_state_posts_require_membership_not_just_an_operator`.
**Outcome:** the Level 5 core invariants hold; one finding — RT-API-02, a
beyond-the-fix gap on RT-API-01 — found, confirmed by induction, and fixed.

## Scope

Level 5 lets an operator ask "what would this case allow under a different
evidence or authority limit?" as a measured counterfactual, kept separate from
the real case and never executable. This round confirms those promises on the
live path and, following `beyond-the-fix`, checks whether the counterfactual
endpoint re-opens a hole the previous round (RT-API-01) closed.

## Threat model

- **Attacker CAN:** act as any configured operator; POST counterfactuals,
  acquisition proposals, abstentions; read every field the responses return.
- **Attacker CANNOT:** forge another operator's token; edit the database.
- **Trust boundary:** case membership (RT-API-01) — reading a case's real state
  requires being a participant in that case.

## Epistemic legend

CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## Level 5 core invariants — CONFIRMED BY INDUCTION

| ID | Invariant | Observed |
|----|-----------|----------|
| L5-iso | A counterfactual writes no real case object | After POST, the `objects` table is byte-for-byte unchanged (no decision, receipt, or prepared action); the counterfactual lands only in the separate `counterfactuals` table |
| L5-stale (fresh) | A new counterfactual is not stale | `stale=false` on creation |
| L5-stale (changed) | It is flagged stale once real inputs change | After the mandate is revoked, `GET /counterfactuals` reports `stale=true` |
| L5-noexec | A counterfactual is not executable | `POST /actions/execute` with a counterfactual id returns 404 — it is not a prepared action |

The isolation and non-executability promises are real: a counterfactual cannot
become a decision, a receipt, or an execution, and it is recomputed against the
real inputs so a stale one is marked rather than silently trusted.

## RT-API-02 — a counterfactual is a read side-channel around the read gate

**Severity:** Medium. **Status:** CLOSED 2026-10-31. **Epistemic level:**
CONFIRMED BY INDUCTION. **Bucket:** software vulnerability (confidentiality /
authorization-granularity), a beyond-the-fix gap on RT-API-01.

**Surprise.** RT-API-01 gated the nine `GET /api/cases/...` read endpoints by
case membership. But `POST /counterfactuals` returns a `Counterfactual` whose
`real` field is the case's actual outcome — `verdict`, `evidence_state`,
`authority_state`, `reasons` (which name the real mandate scope and resources),
and `would_include` (real observation ids). It was guarded by `_operator` only.

**Induction.** A configured operator D with no relationship to `case-001` is
refused on `GET /api/cases/case-001` and `GET /api/cases/case-001/counterfactuals`
(403, per RT-API-01) — yet `POST /api/cases/case-001/counterfactuals` returned
200 with the real outcome: `verdict=forbidden`, `authority_state=denied`,
`reasons` naming `case-001/device-B` and `obs-b1`. A write endpoint leaked
exactly the read RT-API-01 was meant to gate.

**Blast radius (variant analysis).** Probed every case-scoped POST as a
non-member:

| Endpoint | Before fix | Disposition |
|----------|-----------|-------------|
| `POST /counterfactuals` | 200, leaks real outcome | **Fixed** — now requires membership |
| `POST /acquisition-proposals` (propose) | 200, leaks requirement-derived content | **Fixed** — now requires membership |
| `POST /abstain` | reaches the handler and mutates+returns a requirement | **Fixed** — now requires membership |
| `POST /propose-with-muse` | 403 | already gated by `_authenticated_principal` (mandate principal) |
| `POST /actions/{prepare,execute,recover}` | principal-gated | `_authenticated_principal` — stronger than membership |
| `POST /team-records`, `/handoffs`, `/handoffs/accept` | return case state | left as-is: posting makes the actor a participant (`_case_members` counts team and handoff actors), and Level 4 deliberately allows a non-party to resolve a conflict — gating these by prior membership would break that intended flow |
| `POST /evaluations`, `/acquisition-attempts/{id}/reconcile` | return acquisition state | not gated here: both need a case-specific workflow/attempt id a non-member cannot discover (the GET that lists them is membership-gated), and, like the non-party resolver, an independent evaluator may legitimately be a third party. Recorded for the maintainer rather than gated unilaterally. |

**Fix.** `POST /counterfactuals`, `POST /acquisition-proposals`, and
`POST /abstain` now call `_authorize_case_access` (the RT-API-01 membership
check) in place of a bare `_operator`. A non-member is refused 403; a member is
unaffected. Confirmed by induction (D 403, A 200) and regression-locked in
`tests/test_api.py`. Full suite 426 passed.

## Result

Level 5's isolation, staleness, and non-executability hold on the live path. The
one finding was not in the Level 5 mechanics but in its authorization surface: a
counterfactual echoed the real outcome to any operator, re-opening the read gap
RT-API-01 closed. Fixed for the clear leaks; the two lower-reachability siblings
(`evaluations`, `reconcile`) are documented with the reason they are left to a
product decision rather than gated under deadline pressure. This closes the live
authority review across Levels 1–5.
