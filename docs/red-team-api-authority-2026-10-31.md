# Red Team — Live API Authority Boundary — 2026-10-31

**Method:** Abductive Engineering (A–D–I) + `red-team-auditing`.
**Base:** `main` @ `9aecd81` (probes run against the working tree with
`tools/redteam_api_probes.py` added).
**Reproducible evidence:** `tools/redteam_api_probes.py` — boots the real
`krakadyl.api.app:app` under a live uvicorn server with two configured
operators and drives every probe over HTTP. This is induction against a
running server, not code-reading.

## Scope

This round attacks the HTTP authority boundary as it actually runs, not the
core functions in isolation (those were covered by the integrated round on
2026-10-30). The question is whether the live API enforces the delivery
plan's acceptance gate 2 — "an operator token is required for case reads and
writes; the bearer identity, not a request-body name, determines authority" —
under an attacker who speaks HTTP directly.

## Threat model

- **Attacker CAN:** send arbitrary HTTP requests; forge the request body,
  including the `principal` field; replay a prepared action; probe other case
  ids; present no token, an invalid token, or a token belonging to a
  different configured operator.
- **Attacker CANNOT:** invert the SHA-256 operator-token hashes; modify server
  code; edit the SQLite database directly; break SHA-256. (These are the same
  exclusions as prior rounds.)
- **Trust boundary crossed:** operator-bearer authentication and the
  deterministic authority engine (`check_mandate` / `decide`).

## Epistemic legend

CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## Confirmed defenses (induction, live server)

Each probe stated its prediction before execution; all matched.

| ID | Probe | Prediction | Observed | Level |
|----|-------|-----------|----------|-------|
| P1 | Read with no token | 401 | 401 | CONFIRMED BY INDUCTION |
| P2 | Read with an invalid token | 401 | 401 | CONFIRMED BY INDUCTION |
| P3 | Valid operator C prepares on A's mandate | 403 | 403 | CONFIRMED BY INDUCTION |
| P4 | A's token, body claims `principal=C` | 403 | 403 | CONFIRMED BY INDUCTION |
| P5 | Execute the same prepared action twice | 2nd not executed | `executed=False`, "nonce already claimed" | CONFIRMED BY INDUCTION |
| P6 | Read an unknown case | 404 | 404 | CONFIRMED BY INDUCTION |

P3 and P4 together confirm gate 2's core promise live: authority is decided
from the bearer identity and the mandate, never from the caller-supplied
`principal` text. A valid operator who is not the mandate's principal is
refused (P3); a body field that disagrees with the bearer is refused (P4).
The causal chain is in `_authenticated_principal`: it reads the identity from
the token, rejects `identity != mandate.principal` (403), then rejects
`asserted_principal != identity` (403). P5 confirms the one-shot nonce
survives the live execute path, not just the `TestClient` path the suite
exercises.

## Finding

### RT-API-01 — read endpoints authorize the operator, not the case

**Severity:** Low. **Status:** CLOSED 2026-10-31 (fix confirmed by induction;
see Resolution). **Epistemic level:** CODE FACT + CONFIRMED BY INDUCTION.
**Bucket:** authorization-granularity gap (not a bypass; writes were always
scoped).

**Framing correction (fallibilism).** The first probe demonstrated the gap
with operator C reading A's case. That was imprecise: the seed records C as
`verified_by` on obs-a1, so C is a legitimate *participant* — C reading the
case is correct collaboration, not the violation. The real gap is a configured
operator with **no** relationship to the case. Re-probed with investigator-D (a
configured operator who is not a participant): D read the full case overview.
That is the honest demonstration; C was a false witness for it.

**Observation (P7, confirmed live):** operator C, who is a valid configured
operator but is not `case-001`'s mandate principal, issued
`GET /api/cases/case-001` and received `200` with the full case overview —
mission, mandate, observations, custody, hypotheses. Write endpoints do not
behave this way: P3 showed C cannot prepare against A's mandate.

**Why this is not a confirmed vulnerability.** The system does not currently
promise per-case read isolation between operators. Gate 2 promises that reads
require *a* valid operator token (holds) and that the body principal does not
decide authority (holds). Level 4's shared-custody model explicitly puts more
than one investigator on one case, so "any configured operator can read this
case" may be the intended behavior, not a defect. Calling this a breach would
be overclaiming: the seal is intact, writes are locked per mandate, and no
authority was escalated.

**Why it is still worth recording.** There is an authorization asymmetry —
writes are case/mandate-scoped, reads are only operator-scoped — and case
overviews carry evidence detail that a forensic deployment might hold to a
need-to-know standard. Whether that asymmetry is acceptable is a product
decision, and the honest-degradation rule says it must be stated, not left
silent.

**Product decision (maintainer, 2026-10-31):** close it — reads must be
authorized per case.

## Resolution — RT-API-01 (CONFIRMED BY INDUCTION)

Read endpoints now authorize per-case membership, not merely "a valid
operator." `krakadyl/api/app.py` gained `_case_members(case_id)` — the union
of identities the case's own recorded state names (mandate principal, every
`TaskResponsibility` participant on its requirements, every team-record actor,
every shift-handoff actor) — and `_authorize_case_access(case_id,
authorization)`, which all nine `GET /api/cases/...` endpoints now call in
place of a bare `_operator(...)`. A non-participant operator is refused 403;
participants are unaffected. Membership is deliberately derived from
participation rather than a single mandate principal, because Level 4 puts
several investigators on one case — scoping reads to the principal alone would
have broken the independent verifier's own access.

**Honest boundary kept, not hidden.** This is a need-to-know gate among
configured operators. It is not a defense against a malicious insider
operator, who can make themselves a participant by recording a claim — itself
an audited mutation, and out of this round's threat model. The docstring on
`_case_members` states this at the code.

**Prediction stated before the run:** a configured non-participant (D) → 403;
the principal (A) and the independent verifier (C) → 200.

**Induction (live server, `tools/redteam_api_probes.py`):**

```
[P7 D-reads-A-case (non-participant)]      predict 403 | observed 403 | HOLDS
[P8 C-reads-A-case (participant/verifier)] predict 200 | observed 200 | HOLDS
[P9 A-reads-A-case (participant/principal)] predict 200 | observed 200 | HOLDS
```

Regression-locked without a network in
`tests/test_api.py::test_reads_require_case_membership_not_just_an_operator_token`
(D 403; A and C 200; the gate covers `/team`, `/handoff`, `/activity`, not only
the overview). Full suite 423 passed.

## Discarded / confirmed-safe vectors

| Vector | Result | Why |
|--------|--------|-----|
| Body `principal` override of bearer identity (P4) | Refused (403) | `_authenticated_principal` compares asserted principal to the token identity |
| Valid-but-wrong operator acting on a mandate (P3) | Refused (403) | `identity != mandate.principal` rejected before any action |
| Replay of a prepared action (P5) | Refused | one-shot nonce claimed inside the persistence append |
| Unknown / cross-case id (P6) | 404 | `_case_or_404` |
| Missing / malformed bearer (P1, P2) | 401 | `_operator` requires a `Bearer` scheme and a known token |

## Result

Six authority defenses confirmed by induction against the live server; one
read-authorization-granularity gap (RT-API-01) found, its framing corrected
once (C was a participant, not a witness for the gap), and then closed on the
maintainer's decision — reads now authorize per-case membership, confirmed by
induction (D 403; A and C 200) and regression-locked in the suite (423
passed). The finding was kept correctly bucketed throughout: an
authorization-granularity gap among trusted operators, never inflated to a
bypass.
