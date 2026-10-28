# Codex Handoff — Four Independent Branches

Date: 2026-10-27

## Scope and provenance

This handoff covers the four implementation branches requested in
`Desktop/META/11_plan_codex_ramas.md`. Each branch was created independently
from `main` at `447e1099ed86a743841ea976b0a0d626ff709760`; none contains or merges
another branch from this batch.

The branch hashes below were read back from `origin` after each push. Test
counts are the actual outputs observed while that branch was checked out, not
inferences from test files. No branch was merged by Codex.

| Branch | Commit | Scope |
|---|---|---|
| `feat/muse-rate-limit` | `7e82177344c7f0cff796fcb72f564b243dad453a` | Per-process cost bound for billed Muse calls |
| `feat/sqlite-concurrency` | `11d43dac8003b6fe8410461d33b41d19279a48ce` | Serialized SQLite write transactions |
| `feat/typescript-codegen` | `3b3753bdc09149c11f5e99e5f946103394d41cc3` | OpenAPI-generated frontend types |
| `feat/level2-hypothesis-recovery` | `cad0e30f366f9d56d6cfea376d7e99e504f66e1b` | Reviewable recovery questions for invalidated hypotheses |

## `feat/muse-rate-limit`

### What changed

`krakadyl/api/app.py` now applies a lock-protected rolling 60-second admission
window to `propose-with-muse`. The limit defaults to 10 calls per process and
is configured by `KRAKADYL_MUSE_RATE_LIMIT_PER_MINUTE`; zero disables billed
calls, while negative or non-integer values fail during startup. Admission
happens after case and principal validation but before case-summary generation
or the Muse adapter call. An admitted call consumes capacity even when the
adapter later fails because billing may already have occurred.

The F5 entry in `docs/red-team-api-and-frontend.md` now distinguishes the
closed single-process issue from the remaining distributed-deployment limit.

### What verifies it

- `python3 -m pytest -q`: `99 passed`.
- The endpoint regression proves calls 1 through N succeed and N+1 returns
  HTTP 429 without reaching summary construction or the adapter.
- A concurrent admission test proves exactly N of N+K threads are admitted.
- Removing lock use as a temporary mutation made the lock test fail.
- A separate temporary expiry mutation made the expiry test fail.
- A real local Uvicorn and `curl` run with the limit set to zero returned
  `429 Too Many Requests` and `Retry-After: 60`; Muse was not called.

### What I am not sure about

The value 10 and the decision to charge failed adapter attempts against the
window are conservative choices made without deployment or budget data from
Anna. The implementation is intentionally per-process: restarts clear it, and
W workers can admit approximately W times the configured limit. Anna should
confirm that this bound matches the intended deployment before treating F5 as
closed beyond the current single-process scope.

## `feat/sqlite-concurrency`

### What changed

`KrakadylStore` now owns an instance write lock. Every write transaction keeps
the lock across mutation and commit or rollback; reads remain unlocked. SQLite
WAL mode is enabled and verified from a separate observer connection. The
change also fixes a defect discovered during induction: a duplicate nonce
previously returned `False` while leaving the shared connection inside a
transaction, which could block a second writer. The duplicate path now rolls
back before returning.

The F6 entry in `docs/red-team-api-and-frontend.md` records the reproduced
failure mode, the process-local guarantee, and the remaining process boundary.

### What verifies it

- `python3 -m pytest -q`: `95 passed`.
- Two real threads write 25 distinct objects each through one store instance;
  all 50 objects are present afterward and neither thread raises or hangs.
- SQL tracing asserts every `BEGIN`, write, `COMMIT`, and `ROLLBACK` occurs
  while the instance lock is held.
- A regression test proves the duplicate-nonce path leaves
  `connection.in_transaction` false and permits another store to write.
- A no-op-lock temporary mutation made the locking test fail.
- The concurrent test passed in 10 repeated runs during verification.

### What I am not sure about

The lock serializes writers that share one `KrakadylStore` object. It is not an
inter-process lock and does not coordinate separate store instances before
SQLite itself arbitrates them. WAL and rollback behavior were verified, but a
multi-worker deployment was not exercised. Anna should decide whether the
single-process ownership model is the intended near-term boundary or whether a
connection-per-request or dedicated writer design belongs in the next change.

## `feat/typescript-codegen`

### What changed

`frontend/src/api-generated.ts` is generated from FastAPI's live OpenAPI
document with `openapi-typescript@7.13.0`. `frontend/src/api.ts` preserves its
existing exported client surface while aliasing named Pydantic schemas from
the generated file.

The generator has an isolated, exact-version toolchain under
`frontend/tools/openapi-codegen/`: `openapi-typescript@7.13.0` requires
TypeScript 5, while the application intentionally uses TypeScript 7.0.2.
Keeping TypeScript 5.9.3 inside the generator avoids weakening either
dependency contract. `frontend/README.md` documents installation and
regeneration, and `docs/language-decision.md` records the remaining schema
limits.

Two shapes remain deliberately refined by hand in `api.ts` because the Python
API exposes them as generic dictionaries: activity events and execution
manifests. No frontend component was changed.

### What verifies it

- The generated file was produced twice from the same backend schema with the
  same SHA-256 digest:
  `46365d4c934f9c0e9a5da1354fbb67e20db7f1a7802b97fa640e65915338cd2b`.
- `npx tsc -b`: passed.
- `npm run build`: passed.
- `npm run lint`: exited zero with the pre-existing warning at
  `App.tsx:39` still present.
- `python3 -m pytest -q`: `91 passed`.
- A real Chrome run against this checkout's backend completed Prepare then
  Execute and displayed the confirmed prepared action and receipt. Muse was
  not invoked.
- The isolated install used `--ignore-scripts`; npm reported 33 verified
  registry signatures and four attestations during the provenance check.

### What I am not sure about

The checked-in generated file can still drift until a maintainer reruns the
documented command; no CI drift check was added. The two manual refinements are
also a real residual duplication point. I chose not to add explicit Python
response models because that would have exceeded this branch's frontend-only
contract work. Anna should decide whether the next step is a CI regeneration
check, explicit response models, or both.

## `feat/level2-hypothesis-recovery`

### What changed

`krakadyl/core/invalidation.py` now exposes
`propose_hypothesis_recovery`. It can propose a new unresolved
`EvidenceRequirement` only when the original discriminating requirement still
exists and is explicitly unresolvable, and the caller selects another
independently verified requirement already in the case as provenance for an
alternative source class.

The proposal has a deterministic SHA-256-derived ID, preserves the conceptual
predicate and freshness requirement, and resets work to `UNASSIGNED`. It does
not copy observation custody or the failed recovery window, does not mark
anything resolved or verified, does not mutate or relink the hypothesis, and
does not bypass authority blocks. Missing, merely open, observation-specific,
authority-blocked, ambiguous, or unsupported cases close with an explicit
reason. `docs/levels.md` records this as Level 2 Cycle 4 and states that it is
not connected to an endpoint, persistence workflow, or frontend.

### What verifies it

- `python3 -m pytest -q`: `112 passed`.
- The new tests cover successful proposal, deterministic and order-independent
  identity, idempotence, original-object immutability, dangling references,
  rejected and healthy hypotheses, observation and authority boundaries,
  independently verified source provenance, duplicate IDs, and honest
  closures.
- Temporarily changing the proposed responsibility to `VERIFIED_DONE` made
  the positive test fail; the domain validator also rejected the invalid
  object because no verifier or verification method existed.
- An independent post-implementation audit ran 50 directed tests and found no
  remaining blocker after the source-provenance gate was corrected.

### What I am not sure about

Requiring a second independently verified requirement as explicit source
provenance is deliberately stricter than copying the failed requirement's
non-empty `acceptable_source_class`. It is the strongest guarantee available
in the current model, but it may reject a recovery route Anna considers
legitimate. The extra `alternative_source_requirement_id` parameter and the
decision not to relink automatically should receive domain review before any
API or persistence integration is designed.

## Suggested review order

1. Review the hypothesis-recovery semantics and its conservative source gate.
2. Decide whether to replace the two TypeScript refinements with named Python
   response models and whether generated-schema drift belongs in CI.
3. Confirm the Muse limit and deployment topology assumptions.
4. Confirm that SQLite's intended boundary remains one process and one shared
   store instance.

## Skills applied

Shared repository discipline used `abductive-engineering`, `git-discipline`,
`audit-before-patch`, `surgical-patcher`, `software-archaeology`, and
`falsifiable-testing`.

Branch-specific work additionally used:

- Muse: `resource-exhaustion-review`, `secure-by-construction`,
  `validate-at-the-boundary`, and `red-team-auditing`.
- SQLite: `concurrency-reasoning` and `atomic-state-mutation`.
- OpenAPI/TypeScript: `live-contract-compatibility`,
  `dependency-provenance`, `versioned-schema-evolution`, and
  `frontend-testing-strategy`.
- Hypothesis recovery: `invariant-hunting`, `honest-degradation`,
  `llm-out-of-the-loop`, `deterministic-core`, and
  `discriminating-proof`.
- This handoff: `claim-provenance-discipline`,
  `daubert-defensible-writing`, and `remediation-driven-reporting`.

`write-like-me` was evaluated for this document, but no connected writing
reference was retrieved or used. Existing repository documentation supplied
the language and structural conventions instead.

## Handoff boundary

This document does not claim that any branch is production-ready, merged, or
deployed. It claims only the scoped behavior and verification listed above at
the named commits. New evidence about deployment topology, budget policy,
source semantics, API schema shape, or cross-process behavior should reopen
the corresponding review item.
