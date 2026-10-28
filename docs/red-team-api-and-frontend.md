# Security Audit — KRAKADYL API, persistence, and frontend
## Red Team Round 3 (Round 1 and 2 were the core executor/invalidation
engine, already documented inline in `docs/levels.md`'s Level 1/2
sections — this round targets the newest, least-audited surface: the
HTTP API, SQLite persistence, the Muse wiring, and the React frontend.)

**Date:** 2026-10-27
**Method:** Abductive Engineering (A–D–I) + Red-Team Auditing + Variant Analysis + Invariant Hunting
**Scope:** `krakadyl/api/app.py`, `krakadyl/store.py`, `krakadyl/adapters/muse.py`'s API-layer wiring, `frontend/src/**`. Out of scope: `krakadyl/core/*` (already through multiple self-red-team passes, documented in `docs/levels.md`).
**Base:** `main` @ commit `23bafec` (the state right after Muse was wired into the workspace)
**Reproducible evidence:** every CONFIRMED finding below has an exact command; the fixes and their regression tests are in the same commit as this document.

## Threat model

- **Attacker CAN:** send arbitrary HTTP requests to the API (it binds to `127.0.0.1` with CORS restricted to the Vite dev origin today, but nothing in the code itself enforces "localhost only" — that's a deployment choice, not a property of this code); control every request body field; run the frontend in a normal browser with normal JS (no XSS precondition assumed).
- **Attacker CANNOT:** read the SQLite file directly from disk (OS-level access is out of scope); modify the Python source before it runs; forge the Meta Model API's own responses (Muse's output is treated as untrusted regardless).
- **Trust boundary under test:** the HTTP boundary between an arbitrary caller and `krakadyl.core`'s deterministic functions — the same boundary `krakadyl/api/app.py`'s own docstring claims "the UI never re-implements a decision the executor already makes." This round asks whether anything *else* about that boundary was left unenforced.

The sharpest question asked throughout (the "judge test" from `red-team-auditing`): *if asked to prove this system's authority model can't be bypassed through its own API, what would I have to assume?* Finding #1 is exactly what fell out of answering that.

## Epistemic legend
CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## Executive summary

| ID | Severity | Level | Module | Finding | Status |
|----|----------|-------|--------|---------|--------|
| F1 | High | CONFIRMED BY INDUCTION (grep) | `api/app.py` | `Mandate.principal` is declared but read nowhere — identity is not part of any authorization decision at the API boundary | **Fixed** |
| F2 | Medium | CODE FACT | `api/app.py` | Dev router's "a real deployment gates or removes it" was a comment, not a mechanism — no env flag existed | **Fixed** |
| F3 | Low–Medium | CONFIRMED BY INDUCTION | `api/seed.py` / `api/app.py` | `observation_file_path()` interpolates `observation_id` unsanitized; a crafted id resolves outside the case data directory | **Fixed** |
| F4 | Low | PLAUSIBLE HYPOTHESIS, not reproduced | `store.py` | `list()`'s `ORDER BY updated_at` has no tiebreak for same-timestamp writes; `get_case()` reads `list(...)[-1]` as "most recent" | **Fixed** (hardened regardless of reproduction) |
| F5 | Low (cost exposure) | CODE FACT | `api/app.py` | No rate limit on `propose-with-muse` — an unauthenticated caller could loop it and spend the project's Meta API budget | **Mitigated by F1's fix, not fully closed** — see Recommendations |
| F6 | Informational | PLAUSIBLE HYPOTHESIS, not reproduced | `store.py` | Single SQLite connection with `check_same_thread=False`, used from FastAPI's sync threadpool — concurrent writes from two threads are a known SQLite hazard | **Not fixed** — deferred to Level 4 (concurrent investigators), same scope boundary already named in `docs/levels.md` |

## Findings

### F1 — Mandate.principal is never checked anywhere

**Severity:** High **Epistemic level:** CONFIRMED BY INDUCTION **Bucket:** vulnerability (architecture gap), contingent on exposure beyond localhost

- **Surprise / expectation violated:** the project's own README states one of its core, established invariants as "permisos ligados a identidad, recurso, operación, destino, vigencia y alcance" (permissions bound to *identity*, resource, operation, destination, validity, and scope). `Mandate.principal: str` exists as a field since Level 1.
- **Abduction:** if identity were actually enforced, some function in the call graph from an HTTP request to `prepare_evidence_package`/`execute_prepared_action` must read `mandate.principal` and compare it against something caller-supplied.
- **Deduction:** `grep -rn "\.principal\b" krakadyl/` (excluding the field declaration and tests) should show at least one consuming read.
- **Induction:** ran exactly that grep. Zero results. `check_mandate()` (the single place resource/operation/destination get checked, per its own docstring) takes no identity parameter at all. Every action endpoint in `api/app.py` called `_current_mandate(case_id)` and used it without ever asking who the caller was.
- **Causal chain:**
  ```
  HTTP POST /actions/prepare {no identity field at all}
      ↓
  _current_mandate(case_id) — loads the mandate, asks nothing about the caller
      ↓
  prepare_evidence_package(..., mandate=mandate, ...)
      ↓
  check_mandate() — checks resource/operation/destination/validity, NOT who's asking
      ↓
  ALLOWED, for anyone who can reach the endpoint
  ```
- **Threat-model precondition:** the attacker can reach the API at all (today: localhost + the Vite dev origin; the code itself does not enforce that boundary, a reverse proxy or firewall would have to).
- **Fix:** `_assert_principal(mandate, asserted_principal)` now runs in `prepare`, `execute`, `recover`, and `propose_with_muse` (before the billed Muse call, not after — see F5's note), rejecting with 403 when the request's `principal` field doesn't match `mandate.principal`. This is **caller-asserted identity, not cryptographic authentication** — there is still no login/session system, so a caller can still lie about who they are. That remaining gap is real and explicitly not what this fix claims to close; see Recommendations.
- **Regression test:** `tests/test_api.py::test_wrong_principal_is_rejected_on_every_action_endpoint`.

### F2 — The dev router's safety claim was a comment, not a mechanism

**Severity:** Medium **Epistemic level:** CODE FACT **Bucket:** vulnerability (claim/code mismatch) compounding F1

- **Surprise:** `api/app.py`'s own docstring asserted "a real deployment gates or removes this router" as if that were already true.
- **Induction:** `grep -n "dev\|KRAKADYL_ENABLE" krakadyl/api/app.py | grep -i "env\|flag\|enable"` — zero matches before the fix. The comment overclaimed what the code did, the inverse of the usual audit failure (code overclaiming past its comment).
- **Compounds F1:** before F1's fix, anyone reaching the API could call `/api/dev/.../tamper` or `/api/dev/.../revoke-mandate` with no identity check at all, directly corrupting the case the "real" endpoints are supposed to protect.
- **Fix:** dev endpoints moved onto their own `APIRouter`, included in the app only when `KRAKADYL_ENABLE_DEV_ROUTES` (default `"1"`) is not `"0"`.
- **Regression test:** `tests/test_api.py::test_dev_routes_are_absent_when_disabled`.

### F3 — Path traversal in observation file paths

**Severity:** Low–Medium **Epistemic level:** CONFIRMED BY INDUCTION **Bucket:** vulnerability, narrow exploitability

- **Surprise:** `observation_file_path(data_dir, case_id, obs_id)` builds `data_dir/case_id/"raw"/f"{obs_id}.jpg"` by plain f-string interpolation.
- **Deduction:** if `obs_id` contains `../` segments, the resulting `Path`, when resolved, should land outside `data_dir`.
- **Induction:**
  ```python
  from pathlib import Path
  from krakadyl.api.seed import observation_file_path
  p = observation_file_path(Path('/tmp/krakadyl_pt_test'), 'case-001', '../../../../tmp/evil')
  print(p.resolve())  # -> /tmp/evil.jpg
  ```
  Confirmed: resolves outside the intended directory.
- **Bounding the real exploitability, honestly:** the function always appends `.jpg`, and the only live caller (`dev_tamper`, pre-fix) required `path.exists()` before writing — so actual overwrite required a pre-existing `*.jpg` file at an exactly-guessable traversal path. Narrow, but a real primitive, and cheap to close structurally rather than argue about how narrow.
- **Fix:** `dev_tamper` now checks `body.observation_id` against the case's own *known* observation ids (loaded from the store) before ever constructing a path — not a blocklist of `../` patterns, a structural "must already be a real observation of this case."
- **Regression test:** `tests/test_api.py::test_dev_tamper_rejects_a_path_traversal_observation_id`.

### F4 — `store.list()` had no tiebreak for same-timestamp writes

**Severity:** Low **Epistemic level:** PLAUSIBLE HYPOTHESIS (not reproduced as a live bug; fixed anyway because the fix is nearly free and the risk is real)

- **Surprise:** `api/app.py::get_case()` reads `store.list(case_id, "proposed_action", ProposedAction)[-1]` as "the most recently created proposed action." `store.list()` ordered only by `updated_at`, an ISO timestamp string.
- **Deduction:** two objects written within the same timestamp tick have no defined relative order in the result, so `[-1]` could silently return the wrong one.
- **Induction attempted:** Python's `datetime.now(timezone.utc).isoformat()` includes microseconds, so reproducing a real collision under normal wall-clock writes is hard — attempted no forced-collision reproduction (would require monkeypatching the clock, judged not worth the time for a Low-severity, cheap-to-harden finding). **Capped honestly at PLAUSIBLE HYPOTHESIS, not CONFIRMED** — the skill's own rule: no induction run, no higher label, regardless of how cheap the fix is.
- **Fix:** `ORDER BY updated_at, rowid` — SQLite's implicit insertion-order column breaks every tie deterministically.
- **Regression test:** `tests/test_store.py::test_list_breaks_ties_by_insertion_order_not_just_timestamp` (constructs the exact-same-timestamp case directly, since that's the only way to test the ordering clause itself).

### F5 — No rate limit on the billed Muse endpoint

**Severity:** Low, but real (financial, not data) **Epistemic level:** CODE FACT **Bucket:** vulnerability (cost-exposure), **not fully closed**

- **Surprise:** `propose-with-muse` makes a real, billed call to the Meta Model API with no limit on call frequency.
- **F1's fix helps but does not close this:** a caller must now assert the correct `principal` to reach the endpoint — but principal is still self-asserted, not authenticated, so this is a speed bump, not a lock. Anyone who can read the frontend's source (trivially, it's a public bundle) learns the literal string `"investigator-A"` to assert.
- **Not fixed in this round** — a real rate limiter or authenticated-session requirement is more than this round's scope justifies for a single-investigator demo; recorded here so it isn't silently forgotten. See Recommendations.

### F6 — Single SQLite connection shared across FastAPI's threadpool

**Severity:** Informational **Epistemic level:** PLAUSIBLE HYPOTHESIS, not reproduced **Bucket:** hygiene / known architectural limit

- `KrakadylStore` opens one `sqlite3.Connection` with `check_same_thread=False` and reuses it for every request. FastAPI runs sync endpoints in a threadpool, so two concurrent requests execute on two threads against the same connection object — a known SQLite hazard (not thread-safe for concurrent writes without external serialization).
- **Not reproduced** — would require actually racing two real concurrent requests and observing corruption or a lock error; judged out of proportion for a single-demo-user build.
- **Deliberately deferred, not hidden:** this is exactly Level 4's territory ("shared custody, team investigations" — concurrent investigators on the same case), already named as future work in `docs/levels.md`. Noted here so whoever builds Level 4's persistence layer inherits this as a known starting constraint, not a surprise.

## Discarded (non-exploitable) vectors

| Vector | Result | Why it failed |
|---|---|---|
| SQL injection via any store parameter | FALSIFIED | Every query in `store.py` uses `?` placeholders; none interpolate caller data into SQL text. Read the full file; no exceptions found. |
| XSS via Muse's `reasoning` field rendered in the frontend | FALSIFIED | `grep -rn "dangerouslySetInnerHTML\|eval(\|Function(" frontend/src/` — zero matches. React escapes all text content by default; no component bypasses that. |
| Mandate datetime losing timezone awareness across `model_dump_json`/`model_validate_json` round-trip (which would make `check_mandate`'s `now < mandate.valid_from` comparison crash — an availability bug, not an auth bypass) | FALSIFIED | Round-tripped a tz-aware `Mandate` through both calls directly; `tzinfo` survived, comparison succeeded. |
| Cross-case confusion (executing a `prepared_action_id` from case A against case B) | FALSIFIED | `store.get()`'s primary key is `(case_id, kind, obj_id)` — looking up an id under the wrong `case_id` simply returns `None`, caught by the existing 404. Confirmed by reading the query, no live object crosses that key. |
| Nonce replay across cases (nonces are a global table, not case-scoped) | Not a bug — by design | Nonces are `secrets.token_hex(8)`, globally unique regardless of case; global scoping is intentional and doesn't weaken anything, since the value itself is the only thing that must be unique. |
| CORS misconfiguration | Not exploitable as configured | `allow_origins` lists two explicit localhost origins, not `"*"` — this is a tight, if minimal-auth, allowlist for a dev build. |

## Recommendations (not built in this round — recorded for later)

- Replace caller-asserted `principal` with real authentication once there's more than one investigator (Level 4 territory) — a session/login layer that the frontend can't just read out of its own bundle.
- A basic rate limit (even a crude per-process counter) on `propose-with-muse`, independent of identity, as defense in depth against the cost-exposure in F5.
- Revisit `KrakadylStore`'s single shared connection (F6) when Level 4's concurrent-investigator work starts — likely a connection-per-request pattern or an actual write-serializing lock, not assumed away.
