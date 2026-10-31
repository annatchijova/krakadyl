# KRAKADYL — Technical README

This is the unsoftened account, for whoever audits, extends, or replicates the
project. The [primary README](README.md) explains what KRAKADYL is and why it
matters; this document states exactly how it is built, what it guarantees, and
what it does not. Precision is not sacrificed here for accessibility.

**Status of the claims below.** Levels 1–5 are implemented, tested, and
red-teamed on `main` as of 2026-10-31 (see `docs/levels.md` for the per-level
record). Levels 6–7 are roadmap, not built. Test counts and live-run results
are stated with their date and scope; anything not yet measured is labeled as
such rather than rounded up.

**Audience assumption.** You can read Python and TypeScript, you know what a
hash chain proves and what it does not, and you want the exact rule before the
rationale. Rationale is included anyway, after the rule.

## Contents

- [System architecture](#system-architecture)
- [Deterministic core](#deterministic-core)
- [Canonical sealing and the independent verifier](#canonical-sealing-and-the-independent-verifier)
- [Domain contracts](#domain-contracts)
- [Continuity engine](#continuity-engine)
- [Adapters: Muse, Laya, SAM 3.1](#adapters-muse-laya-sam-31)
- [Level 3: acquisition wired into the case](#level-3-acquisition-wired-into-the-case)
- [Level 4: shared custody](#level-4-shared-custody)
- [Level 5: comparable routes](#level-5-comparable-routes)
- [HTTP API](#http-api)
- [Persistence](#persistence)
- [Frontend](#frontend)
- [Threat model and trust boundaries](#threat-model-and-trust-boundaries)
- [Security model and audit history](#security-model-and-audit-history)
- [Determinism and reproducibility scope](#determinism-and-reproducibility-scope)
- [Benchmarks, live evidence, and methodology](#benchmarks-live-evidence-and-methodology)
- [Known limitations](#known-limitations)
- [Non-goals](#non-goals)
- [Failure modes](#failure-modes)
- [Operational constraints](#operational-constraints)
- [Evidence and reproduction](#evidence-and-reproduction)
- [Design decisions and rejected alternatives](#design-decisions-and-rejected-alternatives)
- [Repository map](#repository-map)
- [Document index](#document-index)

## System architecture

One deterministic core decides; everything else proposes, senses, stores, or
renders. No component other than `krakadyl/core` can produce a verdict, and no
component other than `krakadyl/core/executor.py` can publish a package.

```text
                    untrusted                      verified facts
                    ─────────                      ──────────────
Muse Spark ──► ProposedActionCandidate       Mandate (scope/validity/revocation)
(reasoning:          │                       Observation bytes on disk
 display-only)      │                       EvidenceRequirement lifecycle state
                    ▼                       Team conflicts (Level 4)
Laya ──► typed signals ──► human eyes only   Verification graph (structured)
SAM 3.1 ──► annotation sidecar ──► human evaluation
                    │                               │
                    ▼                               ▼
            ┌──────────────────────────────────────────────┐
            │  krakadyl/core: check_mandate + check_evidence │
            │  → decide() → ALLOWED / CONFIRM /             │
            │    GATHER_EVIDENCE / FORBIDDEN                │
            └──────────────────────────────────────────────┘
                    │                         │
              not ALLOWED                   ALLOWED
                    │                         ▼
                    ▼                  PreparedAction (frozen
            Decision only,             snapshot + nonce, TTL 15 min)
            receipt sealed                    │
                                              ▼ (time passes)
                                       execute_prepared_action:
                                       revalidate EVERYTHING against
                                       current state, assemble in temp
                                       dir, verify each copy, atomic
                                       rename, chained receipt
```

Component responsibilities, each in exactly one place:

| Component | Path | Owns |
|---|---|---|
| Policy engine | `krakadyl/core/policy.py` | `decide()` over typed facts only |
| Executor | `krakadyl/core/executor.py` | `check_mandate`, `check_evidence`, prepare/execute, recovery |
| Contracts | `krakadyl/core/models.py` | Pydantic domain objects and validators |
| Continuity | `krakadyl/core/continuity.py` | Evidence-state derivation, `next_move`, urgency |
| Sealing | `krakadyl/core/receipt.py` | Canonical encoder, `CANONICALIZE_VERSION = "1"`, `seal` |
| Verification graph | `krakadyl/core/verification.py` | Structured `VerificationRecord` validation |
| Invalidation | `krakadyl/core/invalidation.py` | Staleness detection, hypothesis review, combined revisions |
| Acquisition contracts | `krakadyl/core/acquisition.py` | Provider-neutral proposal/authorize/capture/evaluate records |
| Acquisition gate | `krakadyl/core/acquisition_store.py` | SQLite admission, budgets, revocation, recovery |
| Team | `krakadyl/core/team.py` | Append-only statements, derived conflicts |
| Handoff | `krakadyl/core/handoff.py` | Shift-handoff views bound to a state digest |
| Counterfactuals | `krakadyl/core/counterfactual.py` | Closed-assumption what-if runs on copies |
| Store | `krakadyl/store.py` | SQLite persistence, atomic writes, nonce + receipt append |
| API | `krakadyl/api/app.py`, `seed.py` | FastAPI over the unmodified core, seeded case |
| Adapters | `krakadyl/adapters/{muse,laya,sam,sam_annotation}.py` | Model/sensor I/O, schema validation, bounds |
| Verifier | `tools/verify_receipt.py` | Stdlib-only independent chain checker |
| Frontend | `frontend/src/` | React workspace; renders server decisions, re-decides nothing |

## Deterministic core

### `decide()`: the precedence order

`krakadyl/core/policy.py::decide` takes four typed inputs — `evidence_state`,
`authority_state`, `outside_mandate_scope`, `resolvable_by_authorized_source`
— and nothing else. Its signature has no parameter shaped to accept raw model
output or document content; that absence is itself a tested structural fact
(`tests/test_policy.py::test_a_classification_signal_alone_never_grants_authority`).
Rules, in order, first match wins:

1. `outside_mandate_scope` or `authority_state == DENIED` → `FORBIDDEN`.
2. `authority_state == EXPIRED` → `FORBIDDEN`.
3. `authority_state == NEEDS_CONSENT` → `CONFIRM` (the decision belongs to the person).
4. `evidence_state` in `MISSING`/`CONFLICTING`/`STALE`:
   - `resolvable_by_authorized_source` → `GATHER_EVIDENCE`;
   - otherwise → `FORBIDDEN`.
5. `SUFFICIENT` + `GRANTED` → `ALLOWED`.
6. Anything else → `FORBIDDEN` (deny by default; the safe default is "don't
   execute", not "ask").

`decide()` returns `(verdict, reasons)`. Reasons are human-readable and never
parsed back into logic anywhere.

### `check_mandate()`: the only mandate check

`krakadyl/core/executor.py::check_mandate` is the single function where a
`(resource, operation, destination)` triple is checked against a `Mandate`.
Both prepare and execute call it at their own time; nothing downstream
re-derives it. Order:

1. `mandate.revoked` → `DENIED` + outside scope.
2. `now < mandate.valid_from` → `DENIED` + outside scope (a mandate cannot be
   confirmed into validity before its own start).
3. `valid_until` passed → `EXPIRED` (inside scope, but closed).
4. `resource` / `operation` / `destination` membership, each checked by exact
   string equality against the mandate's granted sets → `DENIED` + outside
   scope on any miss, naming what is missing.
5. Otherwise → `GRANTED`.

`Mandate` is `frozen=True`: any change (including revocation) forces a new
object with a bumped `revision`, so in-place mutation can never silently
defeat the revision fence at execute time.

### `check_evidence()`: the only evidence derivation

`krakadyl/core/executor.py::check_evidence` derives one `EvidenceState` for a
device-scoped observation set. Observations from other devices are excluded
(by device, recorded in `excluded_devices`), never silently dropped. The
derivation order is fixed — first matching condition wins:

1. Any integrity failure (recomputed SHA-256 of the file on disk differs from
   the custody digest, digest/custody mismatch, or file missing) → `CONFLICTING`.
2. Any logically invalidated observation → `CONFLICTING`.
3. More than one `EvidenceRequirement` governing the same observation →
   `CONFLICTING` (ambiguity is a conflict, never last-write-wins).
4. Any structured verification-dependency failure
   (`validate_verification_dependencies`) → `CONFLICTING`.
5. Any requirement id in the caller-supplied open team-conflict set →
   `CONFLICTING` (a disputed verification is not silently trusted).
6. No included observations → `MISSING`.
7. Any observation with no governing requirement, or whose requirement is not
   independently verified (`continuity.evidence_state_from_requirement`) →
   `MISSING`.
8. Otherwise → `SUFFICIENT`.

Sufficiency therefore requires **both**, for every included observation:
independent `VERIFIED_DONE` on its governing requirement **and** a live digest
match on its bytes. Neither substitutes for the other. A parallel,
machine-readable `failure_reasons: dict[str, str]` names the cause per
observation id; recovery routes consume that dict, never the prose.

### Prepare/execute split

`prepare_evidence_package` decides and snapshots; it executes nothing and
returns `(Decision, PreparedAction | None)` — a `PreparedAction` exists only
on `ALLOWED`. The snapshot records `resource`, `operation`, `destination`,
`resources_touched`, per-observation requirement revisions
(`requirement_revision_digest`), `mandate_revision_checked`,
`source_revision_checked` (combined resource digest), `excluded_sources`,
structured `excluded_resource_reasons`, `expires_at` (`now + TTL`, default 15
minutes), and a `nonce` (`secrets.token_hex(8)`). `PreparedAction` is frozen.

`execute_prepared_action` trusts nothing from prepare time without rechecking
it against current state, in this order: correspondence
(`prepared`/`decision`/`proposed_action` name the same action) → `decision`
still `ALLOWED` → nonce not already consumed (replay) → not expired →
`check_mandate` on the **current** mandate grants → mandate revision unchanged
→ every requirement revision digest unchanged (and the snapshot non-empty) →
`check_evidence` on **current** state is `SUFFICIENT` → combined source
revision unchanged. Any failure produces a sealed not-executed receipt naming
the cause; nothing is published.

Publication is atomic: files are copied into a temp directory
(`out_dir.name + ".tmp-" + nonce`), each copy's digest is verified against
the expected digest immediately after copying (catching change-during-copy
and silent corruption), `manifest.json` is written inside the temp directory,
and only then the temp directory is renamed onto `out_dir`. A mismatch aborts
with nothing published — never a half-written package. The nonce is consumed
only on the success path, so a refused execution does not burn the ability to
retry a corrected action, while an executed one can never run twice.

`assemble_evidence_package` is a thin wrapper calling prepare then execute
back to back for callers with no real gap between the two. It takes the same
Level 3/4 context (`resolvable_requirement_ids`, `conflicted_requirement_ids`)
so the convenience path cannot disagree with the API's full policy path.

### Recovery is a proposal, never auto-applied

`propose_recovery_route` retries the exact same action with exactly the
failing resources excluded (integrity failures, unverified, team-conflicted),
through the unmodified `prepare_evidence_package`/`decide()` pipeline — no new
decision logic, no evidence patched. It refuses to attempt recovery when the
mandate itself is the problem (revoked, expired, narrowed, bumped revision):
excluding a resource cannot restore a missing permission, so it closes
honestly with that reason. If exclusion still yields nothing usable or still
isn't `ALLOWED`, it closes honestly rather than forcing a package. The
recovered manifest's `excluded_resources` list names each dropped resource
and why. The caller must pass the same reduced observation/requirement sets
to `execute`; passing the original untrimmed set makes execute's own
revalidation refuse again, by design.

## Canonical sealing and the independent verifier

One canonical encoder, used everywhere a receipt is hashed:
`krakadyl/core/receipt.py`, `CANONICALIZE_VERSION = "1"`. Type tags keep `1`,
`"1"`, `1.0`, and `True` distinct — `bool` is checked before `int`; `float`
raises `TypeError`, so a float can never silently enter a sealed payload.
Dicts are recursively key-sorted; the version tag is part of the hashed
bytes. `seal(payload, prev_hash)` is SHA-256 over `prev_hash` (when present)
followed by the canonical bytes.

Both outcomes seal: an executed action seals verdict + `executed: True` +
package digest + included count; a refusal seals verdict + `executed: False`.
"This was refused, and here's exactly why" is as permanent a record as "this
executed." The API links sequential execution receipts by passing the latest
persisted receipt hash into the executor; concurrent appends are arbitrated
inside `BEGIN IMMEDIATE` and re-sealed against the predecessor actually won,
so the persisted chain never forks (see KL-005, closed).

`tools/verify_receipt.py` is the independent verifier: stdlib only
(`hashlib` + `json`), and it must never import `krakadyl.core` — it
reimplements the canonicalization rules so the two implementations can
disagree, and that disagreement is what the tool exists to catch. It covers
the JSON-typed subset actually sealed (ids, verdict strings, booleans,
digests, counts) and rejects empty or malformed chains with explicit nonzero
failures. It proves sealing and linkage; it does not reconstruct mandate
scope or the evidence graph from a receipt alone (see KL-002).

## Domain contracts

All contracts live in `krakadyl/core/models.py` as Pydantic models. The
structural rules below are enforced by validators, not by convention; each
names what it refuses.

**Two separate state dimensions.** `EvidenceState`
(`SUFFICIENT`/`MISSING`/`CONFLICTING`/`STALE`) and `AuthorityState`
(`GRANTED`/`NEEDS_CONSENT`/`DENIED`/`EXPIRED`) are independent inputs to
`decide()`. A verdict (`ALLOWED`/`CONFIRM`/`GATHER_EVIDENCE`/`FORBIDDEN`) is
their combination under the precedence order, never either dimension alone.

**Task responsibility is not evidence custody.** `TaskResponsibility` (on
`EvidenceRequirement`) tracks work: owner, acceptance, and a ten-value
`TaskStatus` lifecycle
(`UNASSIGNED → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → REPORTED_DONE →
VERIFIED_DONE`, plus `BLOCKED`/`EXPIRED`/`CANCELLED`/`UNKNOWN`).
`EvidenceCustody` (on `Observation`) tracks the artifact: acquisition, holder
history (`CustodyTransfer`), transformations (`CustodyTransformation`), and
the integrity digest. Completing a task does not demonstrate custody of what
it produced, so the two are never the same object.

**`VERIFIED_DONE` requires recorded independence.** The model validator
rejects `VERIFIED_DONE` without `verified_by` and `verification_method`, and
rejects `verified_by == reported_done_by` unless `verification_method` starts
with `tool:` (an automated check separate from the self-report act).
`validate_assignment=True` closes the post-construction attribute-assignment
bypass; `tests/test_model_invariants.py` proves the bypass stays closed.
Stated at the precision it deserves: the validator runs wherever the model is
constructed or assigned, not yet proven against every persistence or
serialization path — see `docs/levels.md` invariant 4 for the exact boundary.

**Recovery windows have four kinds.** `RecoveryWindowKind` is `KNOWN`
(deadline known), `ESTIMATED` (requires `estimate_basis`: the source and
confidence behind the number), `CONDITIONAL` (requires `condition`: the event
that closes it), or `UNKNOWN`. A single optional datetime cannot distinguish
"no known expiry" from "closes on an event", so the kind is explicit and
`next_move()` never time-ranks what it cannot honestly rank.

**Verification dependencies are a typed graph (structured) or prose (legacy).**
`VerificationRecord`/`VerificationBasis` validate direct and recursive
sources: shared primary ancestry is rejected (two verifications off one
source do not corroborate), self-reference and observation-dependency cycles
are rejected, and current source bytes are rechecked. Legacy requirements
still carry `verified_against` as provenance text with no typed edges; they
do not provide these guarantees until migrated (see KL-001, KL-004).

## Continuity engine

**One derivation point.** `krakadyl/core/continuity.py::
evidence_state_from_requirement` is the only place a requirement's lifecycle
state becomes an evidence state: `unresolvable` → `MISSING`; `resolved` +
verified responsibility → `SUFFICIENT`; `VERIFIED_DONE` without `resolved` →
`CONFLICTING` (the task was verified but the requirement was never marked
resolved — a real inconsistency, surfaced, not papered over); everything
else, including bare `REPORTED_DONE`, → `MISSING`. A claim is never read as a
fact here.

**`next_move()` answers without fabricating.** Input: open requirements.
Output: `primary` (one requirement id) with `alternatives`, or `uncertain`
with the tied candidates, plus `blocked` (attention-worthy but currently
unauthorized) and `conditional_watch` (open work with `CONDITIONAL`/`UNKNOWN`
or absent windows — visible separately instead of sinking in a ranking they
cannot honestly join). Ranking key is recovery-window urgency alone, with the
requirement id as a deterministic tiebreak for ordering only; a genuine tie
on urgency returns `uncertain: True`, never an arbitrary pick. Hypothesis
dependent count is computed deduplicated and exposed as information
(`dependents_count`); it is deliberately not a ranking key, so generating
more hypotheses cannot silently inflate a source's priority. Known gap, not
claimed solved: the count includes listed hypothesis ids regardless of
acceptance status, because `next_move()` does not take `Hypothesis` objects
yet.

**Urgency flags.** `find_urgent_discrepancies` flags only-claimed
requirements on expiring sources: `KNOWN`/`ESTIMATED` windows within the
urgency window (default 30 minutes) with computed `minutes_left`;
`CONDITIONAL` windows unconditionally while only-claimed (`minutes_left` is
`None` — flagged anyway, because unknown timing is not "not urgent").
`UNKNOWN` windows are never flagged: a documented gap (no information to act
on), not a judgment of safety.

**No-blame language is structural.** Discrepancy and handoff reports describe
case state ("this requirement has no independent verification and its source
expires in N minutes"), never the person who made the claim — the same rule
as sibling project Janus's `ORG_FORBIDDEN_WORDS`, applied here in the report
generators rather than left to whoever writes the narration.

## Adapters: Muse, Laya, SAM 3.1

All three adapters sit outside the decision path. Each one's contract states
what it cannot do, and the codebase enforces the boundary rather than
documenting a wish.

**Muse Spark proposes; it never decides** (`krakadyl/adapters/muse.py`).
`propose_action()` sends a compressed, read-only case summary (mission,
mandate marked informational-only, current integrity/verification facts —
never Muse's own prior output fed back in) to the Meta Model API chat
endpoint (`https://api.meta.ai/v1/chat/completions`, model `muse-spark-1.3`,
Standard mode, 30 s timeout, stdlib `urllib` transport, injected for tests)
and validates the response against `ProposedActionCandidate`: four plain
strings (`operation`, `allowed_device`, `destination`, `reasoning`), JSON
schema, no additional properties. A non-matching response raises
`MuseAdapterError` — never coerced into something valid. The candidate then
passes through `check_mandate`/`check_evidence`/`decide()` exactly like a
hand-built action; `reasoning` is display-only and nothing in `krakadyl.core`
reads it. `allowed_device` must be the bare device id (the schema carries an
explicit counter-example, `case-001/device-A`, after the first live call
returned a full path and the deterministic check correctly refused it).
Standard mode is the default on purpose: Contributor mode trades discounted
pricing for Meta's right to train on the content sent, which is never an
acceptable default for case evidence. Missing `META_API_KEY` refuses outright.

**Laya senses; it never authorizes** (`krakadyl/adapters/laya.py`).
`analyze_handoff_note()` turns free text into three typed, bounded signals —
`claims_independent_verification` and `claims_task_complete` (`noul`
probabilities) and `urgency` (a `score` answer normalized to [0, 1] over the
criteria-level index expectation). Nothing in `krakadyl.core` reads this
module's output, and the `/analyze-note` endpoint has no write path to any
requirement, decision, or prepared action — a test asserts case state is
byte-identical before and after the call. Laya runs locally (ModernBERT-family
classifier, no billing; first run downloads a checkpoint from HuggingFace),
pinned exact (`laya==0.4.15`, supply-chain reviewed in
`docs/red-team-laya-integration.md`). The import is lazy and the dependency
optional: without it, the endpoint returns a clear 503 and the rest of the
product is unaffected. Note the checkpoint's own runtime warning that
confidence from affected entries is uncalibrated — the signals inform a
human about what to verify; their precision is not overclaimed.

**SAM 3.1 annotates images; it never identifies, vouches custody, or
establishes causation** (`krakadyl/adapters/sam.py`,
`krakadyl/adapters/sam_annotation.py`). `MetaSamProcessor` calls
`https://api.meta.ai/v1/responses` (model `sam-3.1`) under hard bounds:
10 MiB input, 8 MiB response, 256 prompt characters, 60 s default / 120 s
maximum timeout with an absolute deadline, bounded body reads. Cost is
metered at 2,500 USD-micros ($0.0025) per image against the acquisition
budget. Wire parsing is isolated in `sam_annotation.py`: one pinned profile
(`sam3-image-v1-cdf2e8b5625a3471e6dab3be7127b80fa83beb0d`), at most 4096
records, integers within 2^53 − 1, a strict confidence grammar. A mask is an
annotation candidate attached to the case for human evaluation — never a
verified observation by itself.

## Level 3: acquisition wired into the case

When `decide()` returns `GATHER_EVIDENCE`, Level 3 is the legitimate route it
points at. Lifecycle, each step a typed, persisted record
(`krakadyl/core/acquisition.py`): an open requirement stating a discriminating
question gets an `AcquisitionProposal`; a human holding a real operator token
grants a single-use `AcquisitionAuthorization` (bound to the live capture
mandate's principal, scope, revision, and validity — authorization rechecks
all four before persisting a grant, and a stale proposal cannot receive one);
the operator-mediated source submits a capture; SAM segmentation is opt-in;
an identified person evaluates. A self-evaluation is recorded as a claim;
only an independent evaluator resolves the requirement. Unknown outcomes
(interrupted dispatch, unverified quiescence, missing context) abstain
honestly — `AcquisitionOutcomeUnknown` / `AcquisitionRecoveryRequired` — and
recovery demands verified global quiescence before anything proceeds.

The SQLite gate (`krakadyl/core/acquisition_store.py`,
`SQLiteAcquisitionGate`) serializes admission inside `BEGIN IMMEDIATE`: one
authorization admitted once across concurrent connections, deployment budget
caps enforced across cases, request/dispatch intents rolled back as one
transaction, revocation between phases denying dispatch while preserving the
prior charge. Design: `docs/sqlite-acquisition-gate-design.md`; contract:
`docs/level3-acquisition-contracts.md` and
`docs/provider-neutral-acquisition-contract.md`; case wiring:
`docs/level3-case-wiring.md`.

Acceptance was closed by a live run, not by unit tests alone:
`demo/run_level3_live_closing.py` made real SAM 3.1 calls on two synthetic
captures — one returning empty, one a convincing clock localization — and
independent human evaluation judged both non-discriminating, leaving the
requirement open with nothing auto-promoted. That run is the evidence that
"convincing output does not resolve by itself" holds in practice for the
observed corpus; it does not prove robustness against every future output
(see KL-003).

## Level 4: shared custody

More than one investigator on the same case (`krakadyl/core/team.py`,
`krakadyl/core/handoff.py`). Teammate statements are append-only
`TeamRecord`s, kept apart from what is verified: a claim of completion stays
a claim until someone else verifies it; verification only by a non-claimant;
resolution only by a non-party. Four derived conflict kinds —
`COMPETING_COMPLETION`, `DISPUTED`, `EVIDENCE_MISMATCH`,
`STATUS_CONTRADICTION` — make governed evidence `CONFLICTING` at both
prepare and execute time via the `conflicted_requirement_ids` set. A shift
handoff answers "what do I need to know to pick this up" from recorded
state, bound to the exact view (state digest) it was made from; acceptance
compares live database state under the write lock, moves ownership, never
authority. Details and the adversarial review:
`docs/level4-shared-custody.md`, `docs/red-team-level4-shared-custody.md`.

## Level 5: comparable routes

"What would this case allow under different limits?" as a measured
counterfactual (`krakadyl/core/counterfactual.py`): a closed set of typed
assumptions run through the unmodified pipeline on copies — never on live
case state — each measured as necessary / sufficient-alone, stored outside
case state, never executable, and flagged stale when inputs or time change
the real outcome. Counterfactual accumulation is bounded (an unbounded-growth
finding from the integrated audit was remediated). Details and review:
`docs/level5-comparable-routes.md`,
`docs/red-team-level5-comparable-routes.md`.

## HTTP API

`krakadyl/api/app.py` exposes the unmodified core over FastAPI. Every
endpoint calls `prepare_evidence_package` / `execute_prepared_action` /
`propose_recovery_route` exactly as the demos and tests do — there is no
second notion of "allowed" at the HTTP layer. All case reads and all actions
require an operator Bearer [REDACTED] reads included, so identifiers cannot be
used as existence oracles and unauthenticated callers cannot spend the Meta
API budget.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/cases/{id}` | Case overview (evidence, hypotheses, next move) |
| GET | `/api/cases/{id}/activity` | Append-only activity events |
| GET | `/api/cases/{id}/prepared/{pid}` | Fetch a prepared action |
| POST | `/api/cases/{id}/actions/prepare` | Decide + snapshot (free, deterministic) |
| POST | `/api/cases/{id}/actions/propose-with-muse` | Muse candidate → same prepare pipeline (billed) |
| POST | `/api/cases/{id}/analyze-note` | Laya signals for free text (no case writes; 503 without the extra) |
| POST | `/api/cases/{id}/actions/execute` | Revalidate + publish + chained receipt |
| POST | `/api/cases/{id}/actions/recover` | Recovery proposal (reviewable, never auto-applied) |
| POST | `/api/cases/{id}/observations/{oid}/invalidate` | Typed logical invalidation transition |
| GET | `/api/cases/{id}/acquisition` | Acquisition overview |
| POST | `/api/cases/{id}/requirements/{rid}/acquisition-proposals` | Propose a capture route |
| POST | `/api/cases/{id}/acquisition-proposals/{pid}/authorize` | Single-use human grant |
| POST | `/api/cases/{id}/acquisition-authorizations/{aid}/capture` | Operator-mediated capture (bounded body; SAM opt-in) |
| GET | `/api/cases/{id}/acquisitions/{wid}/observation` | Acquired observation |
| GET | `/api/cases/{id}/acquisitions/{wid}/annotation` | SAM annotation sidecar view |
| POST | `/api/cases/{id}/acquisitions/{wid}/evaluations` | Record an evaluation (claim vs resolving) |
| POST | `/api/cases/{id}/requirements/{rid}/abstain` | Honest close: unresolvable |
| POST | `/api/cases/{id}/acquisition-attempts/{aid}/reconcile` | Reconcile an unknown outcome |
| GET | `/api/cases/{id}/team` | Team records + derived conflicts |
| POST | `/api/cases/{id}/requirements/{rid}/team-records` | Append a teammate statement |
| GET | `/api/cases/{id}/handoff` | Current handoff view |
| POST | `/api/cases/{id}/handoffs` | Record a handoff bound to a state digest |
| POST | `/api/cases/{id}/handoffs/{hid}/accept` | Accept against live state under lock |
| GET | `/api/cases/{id}/counterfactuals` | List measured counterfactuals |
| POST | `/api/cases/{id}/counterfactuals` | Run a closed-assumption what-if on copies |
| POST | `/api/dev/cases/{id}/tamper` | Dev only: corrupt a file on demand |
| POST | `/api/dev/cases/{id}/revoke-mandate` | Dev only: revoke the mandate on demand |
| POST | `/api/dev/cases/{id}/unresolve-hypothesis-requirement` | Dev only: break a discrimination link |
| POST | `/api/dev/cases/{id}/reset` | Dev only: re-seed the case |

**Authentication.** Operator identity comes from `Authorization: Bearer
<token>`. Tokens are configured as `identity=sha256(token)` pairs via
`KRAKADYL_OPERATOR_TOKENS`; plaintext is printed once by
`tools/operator_token.py` and never stored by the runtime. A request-body
`principal` is legacy wire compatibility only: if present it must match the
authenticated identity, but it cannot establish identity. Missing/invalid
token → `401` with a Bearer [REDACTED] wrong-mandate-principal or
body-mismatch → `403`; unconfigured verifier → operator-dependent routes
return `503`, never anonymous acceptance. Execution authenticates the mandate
principal before resolving the prepared-action id, and reloads plus
reauthenticates the mandate after the nonce claim.

**Cost and size guards.** Muse calls are rate-limited per process
(`KRAKADYL_MUSE_RATE_LIMIT_PER_MINUTE`, default 10; process-local, not a
distributed limiter). Laya note input is bounded to 4,000 characters at the
Pydantic boundary. Capture bodies are read through a bounded reader. SAM runs
only with `KRAKADYL_ENABLE_SAM=1` plus `META_API_KEY`.

**Dev router.** `/api/dev/...` exists only to demonstrate staleness/recovery
on demand. It is disabled unless `KRAKADYL_ENABLE_DEV_ROUTES=1`, still
requires a Bearer [REDACTED] enabled, and a real deployment gates or removes it.
Full matrix: `docs/authentication-and-authorization.md`.

## Persistence

`krakadyl/store.py::KrakadylStore` is SQLite (`KRAKADYL_DATA_DIR`, default
`out/api/krakadyl.db`). Every domain object is stored as its own canonical
Pydantic JSON (`objects` table); nonces (`nonces`), activity (`events`), team
records, shift events, counterfactuals, and the acquisition gate state live
in their own tables. Writes go through `atomic_write` / `put_*` helpers that
hold `BEGIN IMMEDIATE`, so a prepare bundle, its decision, its prepared
action, and its activity event commit as one transaction — never a partial
logical result. Nonce consumption persists (`claim_nonce`), closing the
Level 2 replay-across-restart gap. Concurrent receipt appends arbitrate the
serialized head inside the lock and re-seal against the won predecessor;
package assembly itself stays outside the lock — only the short receipt
append is serialized. Single connection, single worker: multi-worker SQLite
hardening is explicitly deferred (see Residual risks).

The seeded case (`krakadyl/api/seed.py`, `case-001`) is the same two-device
synthetic case as `demo/run_case_001.py` — seeded once on first use, then
persistent across restarts and reloads. Seeded mandates are valid 30 days
from 2026-10-27; after expiry every action is correctly `FORBIDDEN` until the
case is re-seeded.

## Frontend

`frontend/` is React 19 + TypeScript (~7.0) + Vite 8 over the API above: case
overview, Evidence, Next move, Acquisition, Team, Activity, Hypotheses, Laya
note, Ask Muse, and a dev-only simulation panel. Every button calls a real
endpoint; nothing in the UI re-decides what the executor decided — Muse
reasoning renders in a panel labeled "not authoritative" next to the
deterministic verdict, and Laya signals render as bars labeled "never marks
anything verified". The operator token lives in React memory only (re-auth
after reload; never localStorage, cookies, or the repo).

API types are generated, not hand-mirrored: `npm run gen:api-types` runs
`openapi-typescript` against the backend's `/openapi.json` into
`src/api-generated.ts` (committed; never hand-edited), with its own
exact-version lockfile because the generator needs TypeScript 5 while the
app compiles with TypeScript 7. Two endpoint-local shapes stay narrowly
refined in `src/api.ts` (`/activity` returns `list[dict]`;
`ExecuteResponse.manifest` is `dict`) — the documented codegen boundary, not
a silent drift risk. No `dangerouslySetInnerHTML`, `eval`, or `new Function`
sinks (checked by source inspection in the integrated audit).

## Threat model and trust boundaries

The standing threat model across the red-team rounds (`docs/red-team-*.md`):

- **Attacker CAN:** send arbitrary HTTP requests; forge any request body
  (including `principal`); replay a prepared action; probe other case ids;
  present no token, an invalid token, or another operator's token; submit
  tampered artifacts and contradictory team claims.
- **Attacker CANNOT:** invert the SHA-256 operator-token hashes; modify
  server code; edit the SQLite database directly; break SHA-256. OS-level
  database/source modification and SHA-256 breaks are out of scope in every
  round — stated, not assumed.

**Trust boundaries crossed, in order:** operator-Bearer [REDACTED] (who is
calling) → mandate scope/validity/revocation (what is permitted) →
observation bytes + requirement lifecycle + verification graph (what is
established) → deterministic verdict → sealed receipt. Untrusted content
(case documents, model summaries, sensor classifications) never crosses into
authority: investigated material, agent instructions, execution permissions,
and installable dependencies are four separate categories, and invariant 6
keeps them separate including across the supply chain (pinned dependencies,
reviewed before pinning).

**What the seal proves, exactly.** A verified chain proves each receipt's
payload is byte-identical to what was sealed and that no entry was inserted,
reordered, altered, or dropped after the fact. It does not prove the mandate
was wise, the evidence true, or the human evaluation correct — those live
outside the sealed payload by design, and KL-002 records that a receipt alone
does not reconstruct the authorization closure for an offline verifier.

## Security model and audit history

Audits here follow the project's own red-team discipline: every finding
carries an epistemic level (code fact / plausible hypothesis / confirmed by
induction / falsified), discarded vectors are part of the deliverable, and
threat models are explicit per round.

- **Round 3 — API, persistence, frontend (2026-10-27).** Found
  `Mandate.principal` unread by any authorization decision (closed with
  Bearer [REDACTED] binding) and the dev router's gate as comment-not-mechanism
  (closed with `KRAKADYL_ENABLE_DEV_ROUTES`), plus a path-traversal primitive
  and a timestamp tiebreak (both fixed). Cost exposure on the billed Muse
  endpoint and single-connection SQLite concurrency were recorded as
  out-of-round, not silently dropped.
- **Laya supply-chain review (2026-10-27).** The `laya` dependency's anomalous
  star/fork ratio was investigated to real causes (funded founder, genuine
  HN launch); pinned exact at the reviewed version.
- **Per-level reviews.** Level 3 acquisition contract, Level 3 case wiring,
  Level 4 shared custody, Level 5 comparable routes, composed authorization,
  verification-graph composition, verification invalidation — each with its
  own `docs/red-team-*.md` report.
- **Integrated round (2026-10-30, `main` @ `a80e10e`).** Fourteen findings
  (handoff fencing, auth-before-lookup ordering, atomic prepare/decision/
  event bundles, mandate reload after nonce claim, receipt-chain extension,
  verifier empty-input handling, Laya input bound, counterfactual growth
  bound, dev-router default-off, among others) — all remediated, each with
  induction probes and regression tests; see "Remediation status" in
  `docs/red-team-full-audit-2026-10-30.md`. SQL injection, observation-ID
  traversal, frontend DOM injection, counterfactual state pollution, and
  self-promoting acquisition results were all **falsified** as vectors in
  the current code.
- **Live API authority boundary (2026-10-31, `main` @ `9aecd81`).** Six
  probes against a running uvicorn server (`tools/redteam_api_probes.py`):
  anonymous/invalid reads → 401, wrong-principal prepare → 403,
  body-principal mismatch → 403, double execute → second not executed
  ("nonce already claimed"), unknown case → 404. All predictions matched.
  One low-severity granularity finding (RT-API-01, read endpoints authorize
  the operator rather than the case) was closed the same day, confirmed by
  induction.

**Residual risks (open, stated, not hidden):** operator tokens are shared
secrets with no expiry, rotation, MFA, or IdP lifecycle — a local-deployment
credential boundary, not production authentication; the single SQLite
connection and process-local Muse limiter need a multi-worker/concurrency
load test before any deployment claim. Production IdP, distributed session
handling, and a distributed cost limiter are deferred extensions, listed in
the delivery plan as such.

## Determinism and reproducibility scope

Stated as scope-then-commitment, because "deterministic" without a scope is
the exact overclaim this document refuses to make.

**Deterministic given identical inputs:** `decide()`, `check_mandate`,
`check_evidence`, `evidence_state_from_requirement`, `next_move`,
`find_urgent_discrepancies`, canonical encoding, and `seal` — pure functions
of their arguments. Prepare-then-execute is deterministic when `now`, the
mandate, the requirements, and the observation bytes are identical; the test
suite pins `now` (fixed timestamps in demos and fixtures) and uses fake
transports, so no test makes a network call.

**Nondeterministic by construction:** `now` at the API boundary (real clock),
`PreparedAction.nonce` (`secrets`, by design — replay protection requires
unpredictability), receipt `created_at` timestamps, and everything downstream
of Muse, Laya, or SAM outputs. Model/sensor outputs are inputs to display
and to human judgment, never to the sealed path — swapping the narrator
backend changes wording only, which is the standing architectural test that
the LLM is out of the decision path.

**Reproducible environment:** Python 3.11 with the committed `uv.lock`
(`uv sync --locked --extra dev --extra api`), frontend via its lockfile on
Node 22, CI pinned by action SHA. The authoritative external verification is
CI run `41127587728` on `a80e10e` (full Python suite incl. HTTP tests,
frontend build + lint, all green). The one known environment caveat is
recorded, not smoothed over: a later local rerun was blocked by a
reproducible `TestClient`/AnyIO worker-thread hang even on a minimal app —
documented as an environment limitation, never presented as a green result.

## Benchmarks, live evidence, and methodology

There is no invented composite score here. The evidence is a set of named,
re-runnable checks, each with its method attached:

- **Standing acceptance scenario** (every level re-measured against it):
  exhausted team, mid-interruption, volatile source about to disappear, a
  task reported done that nobody verified, partial authority.
  `tests/test_continuity.py::test_adversarial_scenario_three_investigators_twenty_minutes`
  is the executable form — real evidence for coordination/continuity
  (invariants 4–5), explicitly not for content isolation (invariant 6), a
  correction recorded in `docs/levels.md` itself.
- **Suite:** 33 test modules (`tests/test_*.py`); last recorded full run
  344 passed (2026-10-30, optional Laya module excluded). Falsifiability is
  enforced per the project's own testing discipline: hypothesis-recovery and
  invalidation tests were also run against temporary verification-bypassing
  mutations and turned red, proving they can fail.
- **Live Muse confirmation (2026-10-27):** `demo/run_case_001_with_muse.py`
  against the real Meta Model API — Muse proposed `package_export` on
  `device-A`, the candidate passed schema validation, `decide()` returned
  `ALLOWED`, real manifest digest and chained receipt produced. An
  adversarial sibling (`demo/run_case_001_muse_adversarial.py`) and a
  contract suite (`tests/test_muse_adversarial_contract.py`) probe the
  hostile-input side.
- **Live SAM closing run (2026-10-30):** `demo/run_level3_live_closing.py`,
  real SAM 3.1 calls on two synthetic captures (empty result; convincing
  clock localization), both independently judged non-discriminating,
  requirement left open. See `docs/sam-live-smoke-2026-10-29.md` and
  `docs/sam-3.1-provider-review-2026-10-28.md` for the provider-side record.
- **Live authority probes (2026-10-31):** `tools/redteam_api_probes.py`,
  six predictions over real HTTP, all matched (see above).
- **Method:** abductive loop (hypothesis → deduced prediction → induction
  against the running system), mandatory refutation attempts, and
  epistemic labeling on every finding — the project's own engineering
  skills (`abductive-engineering`, `red-team-auditing`,
  `discriminating-proof`, `falsifiable-testing`), applied to itself.

## Known limitations

The live register is `docs/known-limitations.md`; this section states the
same entries at the precision an auditor needs, without softening. Open items
are `WARN`, never silent `PASS`.

- **KL-001 — Verification dependency graph is not yet first-class (open).**
  Structured sources validate, reject shared ancestry/self-reference/cycles,
  and recheck bytes; legacy prose provenance has no typed edges, and not
  every external semantic invalidation is forced through the typed atomic
  transition. A source can therefore become semantically invalid while the
  derived requirement bytes stay unchanged, in which case the revision fence
  cannot see the change. Closure: route every invalidation through the typed
  transition and migrate legacy provenance. This bounds the evidence model
  before sealing; it is not a claim that the seal is broken.
- **KL-002 — Standalone receipt verification does not derive authority
  (open).** The verifier proves sealing and linkage, not the mandate scope,
  evidence graph, or verification basis behind a receipt. Consume exports
  with their linked action, decision, snapshot, and provenance.
- **KL-003 — External provider/model behavior is not a correctness guarantee
  (open; authority unaffected).** Muse, Laya, and SAM outputs cannot grant
  authority, resolve evidence, or execute. Live probes cover a bounded corpus
  only — no claim against model drift or every adversarial input.
- **KL-004 — Legacy hypothesis planning lacks typed observation context
  (partially closed).** Structured recovery requires current observation
  context and abstains without it; legacy alternatives still use historical
  state and should display as `WARN`. Execution stays protected: any
  recovered action still passes `check_evidence` and the prepare/execute
  gates.
- **KL-005 — Concurrent API executions need a durable receipt append
  protocol (closed 2026-10-30).** Serialized-head arbitration inside
  `BEGIN IMMEDIATE` with re-sealing against the won predecessor; proven by a
  forced two-thread interleaving (one receipt rooted at the prior head, the
  other linked to the first successor).

Further tracked gaps (each named in code or docs, none claimed solved):
`next_move` counts listed hypothesis ids regardless of acceptance;
`UNKNOWN` recovery windows are never urgency-flagged; `VERIFIED_DONE`
enforcement is validator-scoped, not yet persistence-audited; the Muse rate
limiter is process-local; seeded mandates expire 30 days after seeding.

## Non-goals

- **Deciding what evidence proves.** KRAKADYL keeps the case ready for
  evaluation; verdicts stay with the investigator and inference systems
  (VIGÍA or equivalent). Reducing avoidable `ABSTAIN`s while preserving
  necessary ones is the metric — never pushing a case into looking complete.
- **Production identity.** No IdP, MFA, rotation, or session lifecycle; the
  Bearer [REDACTED] is a local-deployment boundary.
- **Multi-worker serving.** Single SQLite connection, single worker; hardening
  is deferred, explicitly.
- **Real acquisition adapters.** Velociraptor, SIFT, i2, VIGÍA integrations
  are future per-adapter explicit contracts (Level 7), not hardcoded
  assumptions and not present today.
- **A published benchmark dataset.** The standing scenario and red-team
  probes are the current evaluation; open publication is Level 7 work.

## Failure modes

How named failures surface — each row is code behavior, not aspiration:

| Failure | Surface |
|---|---|
| File tampered or substituted after acquisition | `CONFLICTING`, `FORBIDDEN`, sealed refusal naming the observation |
| Mandate revoked / expired / narrowed between prepare and execute | Revalidation refuses; recovery declines (authority problem, not a resource problem) |
| Requirement regressed from `VERIFIED_DONE` after prepare | Revision-digest mismatch refuses at execute |
| Same prepared action executed twice | Second attempt not executed: "nonce already claimed" |
| Prepared action expired (TTL 15 min) | Refused with the expiry timestamp |
| Mandate revision changed (any in-place-attempted edit is impossible: frozen) | Revision mismatch refuses |
| Observation logically invalidated | `CONFLICTING` with the invalidation reason |
| Duplicate requirements govern one observation | `CONFLICTING`, never last-write-wins |
| Open team conflict on the governing requirement | `CONFLICTING` at prepare and execute |
| Package copy corrupts or changes mid-copy | Per-copy digest check aborts; nothing published |
| Acquisition outcome unknown (interrupted, unverified quiescence) | `AcquisitionOutcomeUnknown`: abstain, reconcile, never assume |
| SAM returns empty or non-discriminating output | Annotation candidate recorded; requirement stays open; nothing auto-promotes |
| Operator token missing/invalid/unconfigured | `401` / `401` / `503` — never anonymous acceptance |
| Concurrent receipt appends race | Head arbitration; both receipts persist, chain never forks |
| `laya` extra not installed | `analyze-note` returns 503; core unaffected |
| `META_API_KEY` absent | Muse/SAM paths refuse before any call; deterministic path unaffected |

## Operational constraints

**Environment variables** (all read at process start; no config file):

| Variable | Default | Effect |
|---|---|---|
| `KRAKADYL_DATA_DIR` | `out/api` | SQLite path + observation files root |
| `KRAKADYL_OPERATOR_TOKENS` | unset | `identity=sha256(token)` pairs; unset → operator routes 503 |
| `KRAKADYL_ENABLE_DEV_ROUTES` | `0` | `1` enables `/api/dev/...` (still Bearer-gated) |
| `KRAKADYL_ENABLE_SAM` | unset | `1` plus `META_API_KEY` enables SAM captures |
| `META_API_KEY` | unset | Meta Model API key for Muse + SAM; absent → those paths refuse |
| `KRAKADYL_MUSE_RATE_LIMIT_PER_MINUTE` | `10` | Process-local billed-call limiter |

**Pinned execution contract.** Python 3.11, `uv.lock` (committed), frontend
lockfile, Node 22, CI actions pinned by SHA. Backend serves `:8000`,
frontend dev server `:5173` (`VITE_API_BASE` overrides the API origin).
Core runtime dependency is Pydantic alone; FastAPI/uvicorn, pytest/httpx,
and Laya are separate extras so a minimal deployment carries exactly what it
uses.

**Billed vs free.** `prepare`/`execute`/`recover`, all reads, and Laya
signals are free (Laya runs locally after its one checkpoint download).
"Ask Muse" and every SAM capture are real, billed Meta API calls — separate
buttons and separate endpoints from the free path on purpose, so nothing
accidental spends budget.

**Calendared expiry.** Seeded mandates are valid 30 days from 2026-10-27
(through judging, ~2026-11-26). Past expiry the system is correctly
`FORBIDDEN` everywhere until re-seeded — correct behavior, not a bug, but
plan for it if you demo later.

## Evidence and reproduction

From a clean checkout, Python 3.11:

```text
uv sync --locked --extra dev --extra api
uv run pytest -q tests --ignore=tests/test_laya_adapter.py
cd frontend && npm ci --ignore-scripts && npm run build && npm run lint
```

Backend + frontend (generate operator credentials first — printed once):

```text
python tools/operator_token.py investigator-A investigator-C
export KRAKADYL_OPERATOR_TOKENS='...'   # the printed hash mapping
KRAKADYL_DATA_DIR=out/api uvicorn krakadyl.api.app:app --port 8000
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Deterministic demos (no network, no keys): `demo/run_case_001.py` (two-device
case: allowed package, mandated exclusion, tamper caught, `REPORTED_DONE`
refused), `demo/run_case_002_level2.py` (full staleness → recovery → honest
close sequence, six steps). Live demos (keys required, billed):
`demo/run_case_001_with_muse.py`, `demo/run_case_001_muse_adversarial.py`,
`demo/run_level3_live_closing.py` (rehearsal mode available without keys;
live mode refuses unless guard rails pass). Receipt verification:
`python tools/verify_receipt.py chain.json` (stdlib only; exit 0 + `OK` on
intact, `BROKEN` + nonzero otherwise). Authority probes:
`tools/redteam_api_probes.py` (boots live uvicorn, two operators, six
predictions over HTTP). API smoke: `tools/api_smoke.py` (what CI runs after
pytest). Regenerate frontend types after any Pydantic response-model change:
`npm run gen:api-types` against a serving backend, then commit
`src/api-generated.ts`.

## Design decisions and rejected alternatives

Each entry names the decision, the rejected rival, and the reopen condition —
a decision without a falsifier is a preference, not engineering.

- **Python core.** Chosen per the `language-selection` skill: the sealed-path
  doctrine wants exact-rational arithmetic, and every interop surface (Laya,
  Meta Model API cookbook, VIGÍA/ANNACONDA/ZAYNOR) is verified Python.
  Rejected: Rust (reopen if invalid-state bugs become the dominant failure
  mode in practice), Go (reopen for Level 7's no-Python-env binary),
  TypeScript full-stack (loses the DFIR ecosystem; resolved via the
  Python/TS split instead).
- **TypeScript + React frontend.** Real interactive state from Level 1
  (selection, counterfactual views that must never merge into the case,
  keyboard accessibility). Streamlit lost on interaction control; plain JS
  lost on state complexity. Boundary: Pydantic models are the single source
  of truth, codegen'd into the frontend.
- **Policy in Python, not Rego/OPA — yet.** A separate policy runtime would
  reinforce "the model never touches the decision" by process boundary, but
  migrating rules before the Mandate/Decision schema settles is guaranteed
  rework. Reopen when policy outgrows attribute checks or an external
  auditor needs policy without Python.
- **Muse Standard mode as the only default.** Contributor mode's discount
  buys Meta training rights over case content — never acceptable as a
  default here, even for synthetic evidence. A caller may pass another
  model explicitly; the adapter never chooses it.
- **SQLite, single file.** Fits the case-workspace shape (one investigator
  team, one database file, `BEGIN IMMEDIATE` discipline) with zero
  operational surface. A server database and multi-worker hardening are
  deferred, named, and unclaimed.
- **Local Bearer [REDACTED] not an IdP.** Correct scope for a hackathon-built
  local deployment; production lifecycle (expiry, rotation, MFA, directory)
  is specified as future work, not faked.
- **Prepare/execute split with full revalidation.** The gap between deciding
  and acting is where mandates revoke and files change; trusting the
  earlier verdict would be the TOCTOU this level exists to close.
- **Receipts for refusals.** "Refused, and exactly why" is evidence too —
  an audit trail that only records successes cannot distinguish "never
  attempted" from "attempted and correctly denied".
- **Recovery as reviewable proposal.** The recovered route renders with its
  exclusion and reason before anything executes; auto-applying it would
  collapse the human authorization the mandate exists to require.
- **Four-kind recovery windows; urgency-only ranking.** Corrections from the
  Oct 27 review: a bare datetime conflated "no expiry" with "event-gated",
  and hypothesis-count ranking let hypothesis volume move priority.
- **Frozen models + assignment validation.** Found by self-red-teaming, not
  by review checklist: construction-only validators and mutable snapshots
  bypassed the independence and invalidation guarantees they existed to
  provide. Regression tests prove the bypasses stay closed.

## Repository map

Conceptual layout — what each part is for, not every file:

```text
krakadyl/
├── TECHNICAL_README.md      # this document: the unsoftened account
├── README.md / README.es.md # human-facing primary docs (EN/ES)
├── krakadyl/
│   ├── core/                # deterministic decision engine (no network, no models)
│   │   ├── policy.py        # decide(): precedence over typed facts
│   │   ├── executor.py      # mandate/evidence checks, prepare/execute, recovery
│   │   ├── models.py        # Pydantic domain contracts + validators
│   │   ├── continuity.py    # evidence-state derivation, next_move, urgency
│   │   ├── receipt.py       # canonical encoder (v1) + SHA-256 sealing
│   │   ├── verification.py  # structured verification-graph validation
│   │   ├── invalidation.py  # staleness, hypothesis review, revisions
│   │   ├── acquisition*.py  # Level 3 contracts, routes, SQLite gate
│   │   ├── evaluation.py    # evaluation recording + requirement transitions
│   │   ├── team.py          # Level 4 statements + derived conflicts
│   │   ├── handoff.py       # shift handoffs bound to state digests
│   │   └── counterfactual.py# Level 5 what-if runs on copies
│   ├── adapters/            # model/sensor I/O: schema validation + bounds
│   │   ├── muse.py          # Muse Spark proposals (Standard default)
│   │   ├── laya.py          # typed handoff-note signals (optional)
│   │   └── sam*.py          # SAM 3.1 calls + isolated wire parsing
│   ├── api/                 # FastAPI over the unmodified core + seed
│   ├── store.py             # SQLite persistence, atomic writes, nonce/receipt append
│   └── acquisition_runtime.py # Level 3 runtime orchestration
├── tests/                   # 33 modules: behavioral + regression evidence
├── demo/                    # runnable cases: deterministic + live (keyed)
├── tools/                   # operator tokens, receipt verifier, probes, smoke
├── frontend/                # React + TS workspace (generated API types)
├── docs/                    # levels, contracts, language choice, red-team rounds
└── .github/workflows/ci.yml # locked Python + frontend checks, no Meta creds
```

## Document index

Start here for depth the sections above route to: `docs/levels.md` (the six
invariants, all levels, full build log), `docs/known-limitations.md` (KL-001
to KL-005, live register), `docs/language-decision.md` (full derivation with
rivals), `docs/authentication-and-authorization.md` (trust model, matrix,
verification), `docs/level3-acquisition-contracts.md` +
`docs/provider-neutral-acquisition-contract.md` +
`docs/sqlite-acquisition-gate-design.md` (acquisition),
`docs/level3-case-wiring.md`, `docs/level4-shared-custody.md`,
`docs/level5-comparable-routes.md` (wiring per level),
`docs/red-team-full-audit-2026-10-30.md` +
`docs/red-team-api-authority-2026-10-31.md` (latest integrated verdicts),
`docs/muse-adversarial-probe-2026-10-30.md`,
`docs/sam-3.1-provider-review-2026-10-28.md`,
`docs/sam-live-smoke-2026-10-29.md`, `docs/red-team-laya-integration.md`
(adapter evidence), `docs/terminal-first-and-blame.md` (where invariants 4–5
come from), `docs/presentation-delivery-plan.md` (acceptance gates).

License: Apache-2.0 (`LICENSE`). Public and open from the first commit.
