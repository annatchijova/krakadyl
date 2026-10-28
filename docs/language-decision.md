# Language decision — KRAKADYL

Decided 2026-10-27, via Anna's `language-selection` skill. Full
derivation (forces, rivals, falsification attempt) kept here in short
form; the complete reasoning lives in the session transcript.

## Core (domain model, policy engine, agent orchestration, benchmark harness)

**Chosen: Python.**

Nearly imposed, not just preferred: Anna's own architecture doctrine
requires `fractions.Fraction` (Python stdlib) in any sealed decision
path, and every system KRAKADYL interoperates with is verified Python —
Laya, Meta's own Model API cookbook, and Anna's own VIGÍA, ANNACONDA,
ZAYNOR. No force justified paying a cross-language boundary cost against
that much pre-existing alignment within a 9-day build window.

Rejected: Rust (loses on boundary cost vs. benefit; strongest argument
for it — compile-time-excluded invalid states — is a real reopen
condition if the policy engine's state machine grows past what tests
comfortably cover). Go (loses on ecosystem fit; strongest argument for
it — a single distributable binary for non-technical investigators — is
the reopen condition for Level 7's exportable tooling). TypeScript/Node
full-stack (loses the DFIR ecosystem and the native exact-rational type;
resolved instead via an explicit split with the frontend, not by
discarding TypeScript).

Sub-decision, deferred on purpose: the policy engine's rules could live
in Rego/OPA (declarative, separate runtime from the agent — structurally
reinforces "the model never touches the decision" by process boundary,
not just convention). Not chosen for Level 1 because the Mandate/Decision
schema isn't stable yet; migrating rules before the schema settles is
guaranteed rework. Reopen if: policy complexity grows past simple
attribute checks, or an external auditor needs to read policy without
reading Python.

## Frontend (Mission / Evidence / Next move workspace)

**Chosen: TypeScript + React.**

The workspace has real interactive state (selection, the "if this
changes" counterfactual view that must never silently merge into the
real case, keyboard accessibility, timed transitions) from Level 1 — not
a read-only report. Streamlit/Python lost on interaction control;
plain JavaScript lost because the state is non-trivial from day one.

Boundary: the core's domain objects (Mission/Mandate/Decision/Receipt/...)
are the single source of truth, exposed over an HTTP API. Named Pydantic
response schemas are generated into `frontend/src/api-generated.ts` by
`openapi-typescript`; `frontend/src/api.ts` preserves the client API and
aliases those generated schemas. Regenerate after any response-model
change in `krakadyl/api/app.py`.

Two endpoint-local shapes are not yet fully drift-proof: `/activity`
returns `list[dict]` and `ExecuteResponse.manifest` is `dict`, so OpenAPI
can expose only generic dictionaries. `api.ts` contains narrow local
refinements for the fields the UI reads from those two responses. Fully
removing those refinements requires explicit Python response models in a
separately scoped change; this codegen step does not pretend otherwise.

## Verification

An independent receipt verifier, stdlib-only (`hashlib` + `json`, no
project dependencies), so verifying a receipt never depends on trusting
the same code that produced it.

## Reopen conditions (consolidated)

- Policy engine → Rego/OPA, once Mandate/Decision stabilizes.
- Executor/CLI → a Go binary, once Level 7 needs a no-Python-env artifact.
- Core's state machine → reconsider Rust if invalid-state bugs become the
  dominant failure mode in practice, not in theory.
