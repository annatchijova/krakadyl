# Presentation Delivery Plan

Deadline: 2026-11-04.

## Delivery target

The target is a presentable, defensible investigator workspace, not a reduced
prototype. A reviewer must be able to start the backend, authenticate as an
operator, open the seeded case, inspect the evidence state, prepare and execute
a bounded package, demonstrate stale-state recovery, and walk through the Level
3 acquisition path without the frontend making an independent decision.

Levels 1–5 remain part of the product and their invariants are not traded away
for deadline breadth. The deadline determines which narrative is polished and
demonstrated end to end; it does not lower the standard of authority,
determinism, persistence, or evidence integrity.

## Acceptance gates

1. **Launch:** documented commands start the API and frontend from a clean
   checkout with a known dependency set.
2. **Authentication:** an operator token is required for case reads and writes;
   the bearer identity, not a request-body name, determines authority.
3. **Core narrative:** prepare, execute, stale detection, recovery, and final
   receipt all work against the same SQLite-backed case.
4. **Acquisition narrative:** a bounded capture can be proposed, authorized,
   dispatched through the operator-mediated source, stored with integrity
   metadata, and independently evaluated; unknown outcomes abstain honestly.
5. **Proof:** the sealed decision remains deterministic and the LLM/Muse layer
   cannot change it; the UI renders server decisions and does not reimplement
   policy.
6. **Adversarial review:** red-team the integrated narrative and document any
   remaining WARN/ABSTAIN state instead of presenting it as PASS.

## Work order

### 1. Reproducible execution environment

- Keep the committed `uv.lock` and frontend lockfile as the execution contract.
- Add a single documented environment check that exercises one sync FastAPI
  route and one real API request.
- Verify `npm ci`, build, and lint from a clean checkout.

### 2. Demonstration path

- Run the seeded case from a clean data directory.
- Verify the browser flow with operator authentication and the Level 3 panel.
- Capture the exact commands, environment variables, and expected checkpoints.

### 3. Integrated adversarial pass

- Check authority transitions, replay, stale state, cross-case identifiers,
  tampered artifacts, bounded resource use, and LLM narrator independence.
- Re-run the full suite only after the integrated review, then record exact
  results and known environment limitations.

## Deferred production extensions

- A production identity provider, MFA, or distributed session service.
- Multi-worker SQLite hardening or a distributed Muse cost limiter.
- New levels or breadth that would weaken the completed levels' invariants.

## Live-server verification

An earlier revision of this plan recorded the local AnyIO worker-thread path as
hanging even in a minimal FastAPI application, and concluded the live demo had
to be replaced by CI-only verification. **That blocker does not reproduce as of
2026-10-31** and the conclusion it drove is withdrawn.

Verified on 2026-10-31 against the real, unmodified `krakadyl.api.app:app` under
a live uvicorn server (not `TestClient`): the core narrative —
`GET /api/cases/case-001`, `POST .../actions/prepare`, `POST
.../actions/execute` — returns a sealed, executed receipt over HTTP with
operator-bearer auth, in single-digit milliseconds per request.
`tools/api_smoke.py` reproduces this: it boots the server on an ephemeral port
with a throwaway token and data directory, drives the three calls, asserts the
receipt, and tears everything down. This is the live equivalent of acceptance
gate 3 and the "one real API request" work-order item above.

**Caveat, closed 2026-10-31 in CI.** The first live verification ran in the
local `.venv` (Python 3.12), which is not the locked Python 3.11 environment the
committed `uv.lock` and the CI workflow pin. That gap is now closed: the CI
python job runs `tools/api_smoke.py` under locked 3.11 on a clean runner,
wrapped in an OS-level `timeout 90` so a regression of the original hang fails
the job (exit 124) instead of hanging it. The run on commit `440fd09` passed
the `Live-server API smoke check` step, so the live GET + prepare + execute
narrative is proven under the locked environment, not only under the local 3.12
venv. Record the demo in an environment where `tools/api_smoke.py` has passed.

The freeze tags `freeze-mvp-auth-20261030-173844` and
`freeze-before-redteam-remediation-20261030-175604` are published remotely;
`pre-session-20261031-132449` tags the state before this verification pass.
