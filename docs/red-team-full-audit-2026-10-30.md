# Full Red-Team Audit — 2026-10-30

## Scope and epistemic discipline

This audit covers the live `main` tree at commit `25f85c6` after the ordered
Level 3, Level 4, and Level 5 merges. The threat model is an HTTP caller who
can reach the API, can submit arbitrary JSON and case identifiers, and may hold
one configured operator bearer token. OS-level database or source modification
is out of scope.

Claims below use these levels:

- **CODE FACT** — verified in the live source.
- **RUNTIME-CONFIRMED** — the predicted behavior occurred in a controlled run.
- **PLAUSIBLE HYPOTHESIS** — the source chain is credible but the end-to-end
  interaction was not induced.
- **FALSIFIED** — the proposed behavior did not survive the test.

## Test evidence

- `python3 -m pytest -q tests --ignore=tests/test_laya_adapter.py`: **334 passed**.
- The complete suite was not certified green because `tests/test_laya_adapter.py`
  blocks while loading the external model; it was excluded explicitly and is a
  known environment boundary, not counted as a pass.
- `python3 -m compileall -q krakadyl demo tools`: passed.
- Frontend `npm run build`: passed.
- Frontend `npm run lint`: passed with one existing React warning at
  `frontend/src/App.tsx:44`.

## Findings and remediation

### RT-HANDOFF-01 — acceptance did not fence the full case state

Impact: an accepted handoff could report that no state changed even when an
unrelated requirement changed after the handoff was recorded.

Severity: **medium demonstrated**. The test does not demonstrate unauthorized
capture or export; it demonstrates an integrity and audit-trail fracture in a
multi-operator transition.

Invariant:

```text
accepted.state_changed_since_handoff ==
    (case_state_at_acceptance != case_state_at_handoff)
```

Abduction: `accept_handoff` compared the caller-provided `current.state_digest`
with the stored handoff digest, while the caller could provide a stale view.

Deduction: mutate a requirement not included in the transfer, then accept using
the pre-mutation view; the event should say `True`.

Induction: the unfixed regression test failed with
`state_changed_since_handoff=False` while the unrelated requirement was
`BLOCKED`.

Remediation: `record_handoff` now stores a database-derived state fingerprint,
and `accept_handoff` recomputes it inside `BEGIN IMMEDIATE` before changing any
requirement. Old handoffs without this fence are rejected and must be recreated.
The regression test was observed red before the patch and green after it.

### RT-RESOURCE-01 — unbounded counterfactual accumulation

Impact: an authenticated operator could grow per-case counterfactual storage
without bound; every list operation recomputes staleness for every row.

Severity: **low/medium source-confirmed resource risk**. No availability load
test was run against a production-sized database.

Invariant:

```text
counterfactual_rows(case) <= MAX_COUNTERFACTUALS_PER_CASE
```

Remediation: persistence now enforces a limit of 100 rows per case inside the
write transaction, and the API returns `409` rather than silently degrading.
The limit test fills the boundary and asserts the 101st write is rejected.

### RT-DEV-01 — development mutation routes were enabled by default

Impact: if the API was exposed beyond its intended local/demo boundary,
anonymous callers could reach tamper, mandate-revocation, and requirement
mutation simulations.

Severity: **high conditional on network exposure**; demonstrated as a code and
test fact, not as an internet-exposed deployment.

Remediation: `KRAKADYL_ENABLE_DEV_ROUTES` is now opt-in and defaults to off.
Tests that exercise simulations set `KRAKADYL_ENABLE_DEV_ROUTES=1` explicitly.
The remaining deployment requirement is to keep that flag unset outside a
controlled local/demo environment.

## Residual risks after the bearer-authentication round

The previous audit recorded anonymous reads and caller-asserted Level 1/2
identity. The 2026-10-30 authentication round closed those two gaps with
bearer authentication and mandate-principal binding. The remaining risks are:

1. The bearer credentials are shared secrets configured in the process. They
   have no expiry, rotation, MFA, or independent identity-provider lifecycle;
   this is a deployment boundary, not a claim of production authentication.
2. The single SQLite connection and process-local Muse rate limiter need a
   multi-worker/concurrency load test before being claimed safe for deployment.

The first item requires deciding the identity provider, read scopes, token
lifecycle, and frontend session behavior. The current API deliberately fails
closed when no operator verifier is configured.

## Integrated invariant round — authentication before resource lookup

### RT-AUTH-01 — protected POST routes disclosed case existence before auth

**Severity:** Low–medium information disclosure  **Epistemic level:**
**CONFIRMED BY INDUCTION**  **Bucket:** vulnerability

**Invariant:** an unauthenticated request must not learn whether a case exists;
authentication must precede every case lookup on a protected route.

**Abduction:** the read endpoints and `execute` authenticated before checking
the case, but several other protected POST handlers called `_case_or_404`
first. If true, an anonymous request would receive different status codes for
an existing and nonexistent case.

**Deduction:** call `prepare`, `propose_with_muse`, `analyze_note`, and
`recover` directly with no authorization against `case-001` and
`does-not-exist`; predict `(401, 404)` before the fix.

**Induction:** the live code produced `(401, 404)` for all four handlers at
commit `872354a`. After moving `_operator` before `_case_or_404`, the same
experiment produced `(401, 401)` for all four. The regression test is
`tests/test_api.py::test_anonymous_actions_do_not_reveal_case_existence`.

**Causal chain:**

```text
anonymous POST /api/cases/{id}/actions/*
    -> _case_or_404(id)
    -> 404 for unknown id, continue for known id
    -> _operator(authorization)
    -> 401
```

The corrected chain authenticates before resolving the case. The same ordering
was applied to the Level 3 acquisition, Level 4 team/handoff, and Level 5
counterfactual write routes as a variant sweep.

## Refuted vectors

- SQL injection was **FALSIFIED** by tracing the live query sites: external
  values are bound parameters; dynamic SQL is limited to schema-derived table
  names in the new internal fingerprint helper.
- The previously reported observation-ID path traversal was **FALSIFIED** in
  the current code: tamper requires an existing observation ID and the test
  rejects a traversal payload.
- Frontend direct DOM/script injection was **FALSIFIED** by source inspection:
  no `dangerouslySetInnerHTML`, `eval`, or `new Function` sinks were found.
- Counterfactuals changing real case state or becoming executable were
  **FALSIFIED** by the Level 5 tests and the separate append-only storage path.
- Level 3 results promoting themselves without evaluation were **FALSIFIED**
  by the live Meta closing run and its persisted report.

## Completion criterion

The fixed handoff class is complete when the transaction-bound fingerprint is
present on every newly created handoff and all acceptance paths compare the
live database state under the write lock. The authentication residuals are not
complete until caller identity and read access are bound to a real session or
bearer credential on every consequential path.

Skills used: `discriminating-proof`, `invariant-hunting`, `falsifiable-testing`,
`concurrency-reasoning`, `distributed-write-atomicity`,
`resource-exhaustion-review`, `secure-by-construction`, `audit-before-patch`,
`surgical-patcher`, `remediation-driven-reporting`, and `git-discipline`.
