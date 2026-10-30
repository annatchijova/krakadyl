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

## Current blocker

The local Python environment's AnyIO worker-thread path hangs even in a minimal
FastAPI application. This is an environment reproducibility blocker, not a
Krakadyl application defect. CI now has a locked Python 3.11 workflow so the
verification can run on a clean runner outside this sandbox.

The freeze tag `freeze-mvp-auth-20261030-173844` is published remotely before
the next significant mutation.
