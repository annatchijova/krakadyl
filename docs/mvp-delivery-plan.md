# MVP Delivery Plan

Deadline: 2026-11-04.

## Delivery target

The MVP is a coherent investigator workspace, not a feature collection. A
reviewer must be able to start the backend, authenticate as an operator, open
the seeded case, inspect the evidence state, prepare and execute a bounded
package, demonstrate stale-state recovery, and walk through the Level 3
acquisition path without the frontend making an independent decision.

The existing Level 4 and Level 5 capabilities remain part of the product, but
the deadline gate is the end-to-end case narrative above. We will reduce depth
before reducing the authority, determinism, persistence, or evidence-integrity
invariants already established by Levels 1–5.

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

- Pin or otherwise constrain the Python API/test stack after identifying a
  working FastAPI/Starlette/AnyIO combination.
- Add a single documented environment check that exercises one sync FastAPI
  route and one real API request.
- Keep the existing frontend lockfile and verify `npm ci`, build, and lint.

### 2. Demonstration path

- Run the seeded case from a clean data directory.
- Verify the browser flow with operator authentication and the Level 3 panel.
- Capture the exact commands, environment variables, and expected checkpoints.

### 3. Integrated adversarial pass

- Check authority transitions, replay, stale state, cross-case identifiers,
  tampered artifacts, bounded resource use, and LLM narrator independence.
- Re-run the full suite only after the integrated review, then record exact
  results and known environment limitations.

## Explicit non-goals before the deadline

- A production identity provider, MFA, or distributed session service.
- Multi-worker SQLite hardening or a distributed Muse cost limiter.
- New levels or breadth that would weaken the completed levels' invariants.

## Current blockers

- The local Python environment's AnyIO worker-thread path hangs even in a
  minimal FastAPI application. This is an environment reproducibility blocker;
  it is not currently classified as a Krakadyl application defect.
- The freeze tag `freeze-mvp-auth-20261030-173844` exists locally. Pushing it
  was attempted but GitHub DNS was unavailable; retry before the next
  significant mutation.
