# Level 3 — acquisition wired into the case

Status (2026-10-30): implemented on `feat/level3-case-acquisition`, offline-verified, driven end to end in a real browser against a capture-only deployment. **The level-closing live SAM run has not happened** — see "What is still open" below. Level 3 is therefore not claimed complete.

Before this change the acquisition contract (`core/acquisition.py`), the SQLite gate (`core/acquisition_store.py`), the Meta SAM processor and the sidecar parser all existed, but nothing connected them to a case: `executor.py` passed `resolvable_by_authorized_source=False`, no endpoint could propose or authorize a capture, and no code could record an `EvidenceEvaluation`.

## What now exists

| Piece | Where | What it decides |
|---|---|---|
| Discriminating question on a requirement | `EvidenceRequirement.discriminating_question`, `.answer_classes` | No question with ≥2 distinct answer classes → no capture can be proposed. Part of the requirement, so the gate's need digest covers it: rewording it after approval makes the approval stale. |
| Route detection | `core/acquisition_routes.py` | Deterministic: open requirement + question + ≥1 dependent hypothesis + exactly one configured source for its `acceptable_source_class` + a current capture mandate granting `capture` on that source. The refusal names the first missing condition. More than one matching source is refused, not silently picked. |
| Policy wiring | `prepare_evidence_package(resolvable_requirement_ids=…)` | `GATHER_EVIDENCE` only when evidence is MISSING solely because of unverified requirements and *every* one has a route. Integrity failures are never resolvable by a new capture. Default (empty) keeps the Level 1/2 behavior exactly. |
| Evaluation | `core/evaluation.py` | The only writer of `EvidenceEvaluation` and the only code an evaluation may use to move a requirement. Never touches a hypothesis. |
| Deployment runtime | `krakadyl/acquisition_runtime.py` | Operator token identity, mandate-principal scope, finite budgets, local retention, write-once artifacts, operator-mediated capture, opt-in SAM. Fails closed. |
| HTTP | `api/app.py` (Level 3 section) | Propose, authorize, capture (raw image body), observation/annotation read, evaluate, abstain, reconcile. |
| UI | `frontend/src/components/AcquisitionPanel.tsx` | Renders the server's view; makes no decision of its own. |

## Decisions

### D1. An evaluation reuses claim vs. verification instead of inventing a parallel state

- `SUPPORTS_REQUIREMENT` by an evaluator who is neither the acquisition actor nor the earlier claimant → requirement `resolved`, `VERIFIED_DONE`, `verification_method = independent-evaluation:<criterion>@<version>`, `verified_against` names the evaluation id and observation digest.
- `SUPPORTS_REQUIREMENT` by the acquisition actor → `REPORTED_DONE` only. Evidence state stays MISSING and `find_urgent_discrepancies` flags it like any other unverified claim.
- `CONTRADICTS`, `NO_DISCRIMINATING_CHANGE`, `INSUFFICIENT_OR_INVALID` → requirement unchanged. The evaluation is recorded and visible; the next step (another route or an abstention) is a person's decision.

*Rejected:* letting any `SUPPORTS` resolve the requirement (re-creates the exact "reported done, nobody verified" gap KRAKADYL exists for); refusing self-evaluations outright (loses a real fact — the investigator's own reading — instead of recording it as what it is).

*Revisit when:* a named inference mechanism (e.g. VIGÍA) becomes an evaluator. `evaluator_type` already allows `named_inference_mechanism`; the API currently records only `human`.

### D2. CONTRADICTS does not close or flip anything

A contradicted predicate is knowledge, but turning it into a requirement or hypothesis state needs a decision about what "contradicted" means for each dependent hypothesis. Today the evaluation is shown, the requirement stays open, and `find_hypotheses_needing_review` keeps flagging the dependent hypothesis. *Known gap:* the route stays available, so the UI still offers another capture after a contradiction. *Revisit:* when Level 4 adds explicit conflicting-claim handling.

### D3. Abstention is explicit and refused while a capture could still land

`abstain_requirement` sets `unresolvable` with the actor and the ids of every evaluation it followed. It is refused while any workflow for that requirement is `active` or `unknown`: abstaining over a capture whose outcome is unknown would hide it.

### D4. Every write compares the revision the human saw

Evaluation and abstention take `expected_requirement_revision` and re-read the requirement inside the same SQLite transaction. A requirement changed between display and submission → 409, nothing written.

### D5. Identity is a proven bearer token, not an asserted name

`KRAKADYL_OPERATOR_TOKENS` holds `identity=sha256(token)` pairs only (`tools/operator_token.py` generates them). The Level 1/2 endpoints still use the caller-asserted `principal` documented in `red-team-api-and-frontend.md`; none of the Level 3 endpoints do. *Limits, stated plainly:* shared secrets, no expiry, no rotation, no MFA, no per-request replay protection beyond TLS. This is authentication sufficient for a local single-team deployment, not an identity provider. *Revisit:* before any multi-team or network-exposed deployment.

### D6. The source is the investigator

KRAKADYL cannot point a camera at anything. `OperatorIntakeSource` returns exactly the bytes the authorizing operator submits in the dispatching request, only after the gate commits the attempt's dispatch intent. Bytes are held in memory until then; a refused admission persists nothing (tested). The capture specification records the instructions the human approved.

### D7. Capture authority is a separate mandate

`mandate-capture-001` grants `capture`/`derive_annotation` on `case-001/operator-intake` only. The package-export mandate is unchanged, so no Level 1/2 check sees a wider scope than before. Its principal is the only identity that may authorize and dispatch.

### D8. SAM needs a key **and** an explicit opt-in

`KRAKADYL_ENABLE_SAM=1` plus `META_API_KEY`. A key alone never enables billed calls; without SAM the proposal carries no processing plan and the retention destination is `local-only`. With SAM, the proposal's retention decision names the third-party transfer category and the Meta API destination, and the human sees both before authorizing.

### D9. Budgets are finite and configured, not inferred

Defaults: 4 SAM images per requirement, 20 per case/mandate, 40 per deployment (at the public USD 0.0025 image price), with matching byte/duration caps and zero video frames. They are enforced by the existing gate's reservation ledger.

## Falsifiers (each has a test)

- A capture or annotation changes a requirement without an evaluation → `test_independent_supporting_evaluation_…` asserts the requirement is byte-identical after acquisition.
- A self-evaluation verifies → negative control: forcing `independent = True` makes `test_self_evaluation_is_only_a_claim…` fail.
- A stale revision is applied → negative control: removing the revision comparison makes `test_stale_revision_is_refused…` fail.
- `GATHER_EVIDENCE` without a route → negative control: hardcoding `False` again makes `test_unverified_evidence_with_a_route_for_every_gap_is_gather_evidence` fail.
- Wrong token, non-principal token, someone else's grant, replayed grant, changed requirement, non-image body, mismatched Content-Type → no dispatch, no persisted artifact (runtime and API tests).
- UNKNOWN outcome → evaluation, abstention and a new acquisition are all refused until a human reconciles; then a new acquisition proceeds (API test).
- Tampered stored artifact → read refused and not served.

## Verification snapshot — 2026-10-30

- `pytest`: 261 passed before the red team, 270 after (Python 3.13, fresh venv). Offline demos `run_case_001.py` and `run_case_002_level2.py` still pass.
- Frontend: `tsc -b`, `oxlint` (one pre-existing warning in `App.tsx`), `vite build` clean.
- Browser (Playwright, Chromium): capture-only deployment with two operator tokens. Proposed → authorized → uploaded a generated PNG → investigator-A evaluated `supports` (shown "claimed, not verified") → investigator-C evaluated `supports` (shown "resolved · verified"). No page errors.
- SAM box overlay: verified in the browser after the red team, with a fake SAM transport (no Meta call).

## Red team

Done after the first four commits; eight findings reproduced and fixed (evaluation bound to the approved question, reconciliation limited to the authorizer, integrity re-verified at evaluation, completed captures evaluable after a failed SAM phase, authenticated evidence reads, authenticated dev reset, owner-only abstention, earlier claimant preserved). See [red-team-level3-case-wiring.md](red-team-level3-case-wiring.md), which also lists the accepted residual risks.

## What is still open — and blocks calling Level 3 complete

1. **The live closing run.** Ready to execute: `demo/run_level3_live_closing.py` (rehearse first with `--dry-run`). It sends only two script-generated PNGs, spends exactly two SAM image calls (USD 0.005 at list price) with the gate's deployment budget set to the same ceiling, checks automatically that neither capture nor annotation promoted anything, asks a human for each evaluation, and writes `out/level3-closing/<timestamp>/report.json`. It refuses to start without `META_API_KEY`, `--max-usd-micros 5000` or more, and `--meta-retention-reviewed`. Original requirement: `level3-acquisition-contracts.md` requires a real SAM call on a real capture that returns a technically valid but non-discriminating result, plus a separate adversarial run with a convincing incorrect annotation. Both need: the user's approval of the spend ceiling (≈USD 0.01 for four images), a decision on what material is sent to Meta (synthetic only), and a current check of Meta's retention terms. Not run here.
2. Evaluator contract for a named inference mechanism (D1).
3. Contradiction semantics (D2).
4. Identity beyond shared tokens (D5).
