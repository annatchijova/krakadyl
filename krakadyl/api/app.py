"""HTTP API exposing the real core — per `docs/language-decision.md`,
the domain objects are the single source of truth, exposed over HTTP;
the frontend never re-implements any decision logic. Every endpoint
here calls the same, unmodified `krakadyl.core` functions the demo
scripts and test suite already exercise — a discrepancy between what
the UI shows and what the executor actually does is an integration bug
to fix here, never a reason to add a second, UI-side notion of
"allowed."

Dev-only endpoints (`/api/dev/...`) are clearly separated from the
investigative ones: they exist to demonstrate Level 2's staleness/
recovery mechanism (tampering a file, revoking a mandate) the way an
investigator would never deliberately do to their own case — a real
deployment would gate or remove this router entirely, not expose it
next to the real actions.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from krakadyl.adapters.laya import LayaAdapterError, analyze_handoff_note
from krakadyl.adapters.muse import MuseAdapterError, propose_action
from krakadyl.api.seed import CASE_ID, ensure_seeded, observation_file_path
from krakadyl.core.continuity import evidence_state_from_requirement, next_move
from krakadyl.core.executor import (
    DEFAULT_PREPARED_ACTION_TTL,
    execute_prepared_action,
    prepare_evidence_package,
    propose_recovery_route,
    verify_observation_integrity,
)
from krakadyl.core.invalidation import find_hypotheses_needing_review
from krakadyl.core.models import (
    Decision,
    EvidenceRequirement,
    EvidenceState,
    Hypothesis,
    Mandate,
    Mission,
    Observation,
    PreparedAction,
    ProposedAction,
    Receipt,
)
from krakadyl.store import KrakadylStore

DATA_DIR = Path(os.environ.get("KRAKADYL_DATA_DIR", "out/api"))
DB_PATH = DATA_DIR / "krakadyl.db"

app = FastAPI(title="KRAKADYL API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = KrakadylStore(DB_PATH)
ensure_seeded(store, DATA_DIR)


def now() -> datetime:
    return datetime.now(timezone.utc)


def _case_or_404(case_id: str) -> None:
    if not store.case_exists(case_id):
        raise HTTPException(404, f"no such case: {case_id}")


def _load_observations(case_id: str) -> list[Observation]:
    return store.list(case_id, "observation", Observation)


def _load_requirements(case_id: str) -> list[EvidenceRequirement]:
    return store.list(case_id, "requirement", EvidenceRequirement)


def _load_hypotheses(case_id: str) -> list[Hypothesis]:
    return store.list(case_id, "hypothesis", Hypothesis)


def _current_mandate(case_id: str) -> Mandate:
    mandate = store.get(case_id, "mandate", "mandate-001", Mandate)
    if mandate is None:
        raise HTTPException(404, "case has no mandate")
    return mandate


def _assert_principal(mandate: Mandate, asserted_principal: str) -> None:
    """Found by red-team review: `Mandate.principal` existed as a field
    but was read NOWHERE in the codebase — identity was never part of
    the authorization decision at the one layer (this HTTP API) where a
    caller could actually be someone other than who they claim, despite
    the architecture's own stated invariant that permissions are bound
    to identity, resource, operation, destination, and validity.

    This is CALLER-ASSERTED identity, not cryptographically verified —
    there is no login/session system yet, so a caller can still lie
    about who they are. That remaining gap is real and is documented in
    docs/red-team-api-and-frontend.md, not hidden behind this check.
    What this closes is narrower but real: the mandate's principal is
    now actually consulted, instead of being a decorative field no code
    path ever reads.
    """
    if asserted_principal != mandate.principal:
        raise HTTPException(
            403,
            f"this mandate is scoped to principal '{mandate.principal}'; "
            f"request asserted '{asserted_principal or '(none)'}'",
        )


def _observation_files(case_id: str, observations: list[Observation]) -> dict[str, Path]:
    return {o.id: observation_file_path(DATA_DIR, case_id, o.id) for o in observations}


def _proposed_action(case_id: str, allowed_device: str, destination: str) -> ProposedAction:
    return ProposedAction(
        id=f"action-{uuid.uuid4().hex[:10]}",
        operation="package_export",
        arguments={"device": allowed_device, "destination": destination},
        expected_effect=f"assemble a reviewer-ready package of {allowed_device}'s evidence only",
        mission_id=case_id,
    )


def _case_summaries(case_id: str) -> tuple[str, str, str]:
    """Builds Muse's three inputs from the CURRENT live case state, not
    a hardcoded narrative — the whole point of wiring Muse into the
    workspace instead of a fixed demo script. Only facts already
    verifiable through this module's own checks go in; nothing here is
    Muse's own prior output (no feedback loop where a model's words
    become the next model call's "fact").
    """
    mission = store.get(case_id, "mission", case_id, Mission)
    mandate = _current_mandate(case_id)
    observations = _load_observations(case_id)
    requirements = _load_requirements(case_id)
    files = _observation_files(case_id, observations)
    requirements_by_obs = {r.observation_id: r for r in requirements if r.observation_id}

    mission_summary = mission.objective if mission else case_id

    # Devices are named bare ("device-A"), never as the combined
    # "mission_id/device" resource path — found by self-red-teaming the
    # first live Muse call wired into this endpoint: showing the raw
    # path here led Muse to copy it verbatim into allowed_device,
    # which prepare_evidence_package then doubled into
    # "case-001/case-001/device-A" and rejected as out of scope.
    allowed_devices = sorted({r.rsplit("/", 1)[-1] for r in mandate.resources})
    mandate_summary = (
        f"Allowed device(s): {', '.join(allowed_devices)}. Operations: {', '.join(mandate.operations)}. "
        f"Destinations: {', '.join(mandate.destinations)}."
    )
    if mandate.revoked:
        mandate_summary += f" REVOKED: {mandate.revoked_reason}."

    lines = []
    for o in observations:
        req = requirements_by_obs.get(o.id)
        integrity = (
            "integrity ok"
            if verify_observation_integrity(o, files.get(o.id, Path("/nonexistent")))
            else "INTEGRITY FAILED (file no longer matches its acquired digest)"
        )
        verified = (
            "independently verified"
            if (req is not None and evidence_state_from_requirement(req) == EvidenceState.SUFFICIENT)
            else "NOT independently verified"
        )
        lines.append(f"{o.id} ({o.source}): {integrity}, {verified}")
    case_summary = "\n".join(lines) if lines else "no observations recorded"

    return mission_summary, mandate_summary, case_summary


def _persist_prepare_result(
    case_id: str, proposed_action: ProposedAction, decision: Decision, prepared: Optional[PreparedAction]
) -> None:
    ts = now().isoformat()
    store.put(case_id, "proposed_action", proposed_action, ts)
    store.put(case_id, "decision", decision, ts)
    if prepared is not None:
        store.put(case_id, "prepared_action", prepared, ts)


# --- response shapes (UI-facing views composed from the real domain
# objects — these add display-only computed fields, never a second
# notion of what's allowed) ---


class EvidenceItem(BaseModel):
    observation: Observation
    in_mandate_scope: bool
    integrity_ok: bool
    requirement_id: Optional[str]
    requirement_status: Optional[str]
    independently_verified: bool


class HypothesisItem(BaseModel):
    hypothesis: Hypothesis
    needs_review: bool
    review_reason: Optional[str]


class CaseOverview(BaseModel):
    mission: Mission
    mandate: Mandate
    evidence: list[EvidenceItem]
    hypotheses: list[HypothesisItem]
    latest_prepared_action: Optional[PreparedAction]
    latest_decision: Optional[Decision]


class PrepareRequest(BaseModel):
    principal: str
    allowed_device: str = "device-A"
    destination: str = "reviewer-authorized"


class PrepareResponse(BaseModel):
    decision: Decision
    prepared: Optional[PreparedAction]


class MuseProposeRequest(BaseModel):
    principal: str


class MuseProposeResponse(BaseModel):
    muse_operation: str
    muse_allowed_device: str
    muse_destination: str
    muse_reasoning: str
    decision: Decision
    prepared: Optional[PreparedAction]


class AnalyzeNoteRequest(BaseModel):
    principal: str
    note_text: str


class AnalyzeNoteResponse(BaseModel):
    claims_independent_verification: float
    claims_task_complete: float
    urgency: float


class ExecuteRequest(BaseModel):
    principal: str
    prepared_action_id: str


class ExecuteResponse(BaseModel):
    receipt: Receipt
    manifest: Optional[dict]


class RecoverRequest(BaseModel):
    principal: str
    allowed_device: str = "device-A"
    destination: str = "reviewer-authorized"


class RecoverResponse(BaseModel):
    attempted: bool
    excluded_resources: list[str]
    decision: Optional[Decision]
    prepared: Optional[PreparedAction]
    closed_reason: Optional[str]


class TamperRequest(BaseModel):
    observation_id: str


class RevokeMandateRequest(BaseModel):
    reason: str = "case reassigned to another unit"


# --- read endpoints ---


@app.get("/api/cases/{case_id}", response_model=CaseOverview)
def get_case(case_id: str) -> CaseOverview:
    _case_or_404(case_id)
    mission = store.get(case_id, "mission", case_id, Mission)
    mandate = _current_mandate(case_id)
    observations = _load_observations(case_id)
    requirements = _load_requirements(case_id)
    hypotheses = _load_hypotheses(case_id)
    files = _observation_files(case_id, observations)

    requirements_by_obs = {r.observation_id: r for r in requirements if r.observation_id}
    in_scope_devices = {r.split("/")[-1] for r in mandate.resources}

    evidence_items = []
    for o in observations:
        req = requirements_by_obs.get(o.id)
        evidence_items.append(
            EvidenceItem(
                observation=o,
                in_mandate_scope=o.source in in_scope_devices,
                integrity_ok=verify_observation_integrity(o, files.get(o.id, Path("/nonexistent"))),
                requirement_id=req.id if req else None,
                requirement_status=req.responsibility.status.value if req else None,
                independently_verified=(req is not None and evidence_state_from_requirement(req) == EvidenceState.SUFFICIENT),
            )
        )

    flagged = dict(find_hypotheses_needing_review(hypotheses, requirements))
    hypothesis_items = [
        HypothesisItem(hypothesis=h, needs_review=h.id in flagged, review_reason=flagged.get(h.id))
        for h in hypotheses
    ]

    proposed_actions = store.list(case_id, "proposed_action", ProposedAction)
    latest_prepared = None
    latest_decision = None
    if proposed_actions:
        latest_action = proposed_actions[-1]
        latest_prepared = store.get(case_id, "prepared_action", f"prepared-{latest_action.id}", PreparedAction)
        latest_decision = store.get(case_id, "decision", f"decision-{latest_action.id}", Decision)

    return CaseOverview(
        mission=mission,
        mandate=mandate,
        evidence=evidence_items,
        hypotheses=hypothesis_items,
        latest_prepared_action=latest_prepared,
        latest_decision=latest_decision,
    )


@app.get("/api/cases/{case_id}/activity")
def get_activity(case_id: str) -> list[dict]:
    _case_or_404(case_id)
    return store.list_events(case_id)


@app.get("/api/cases/{case_id}/prepared/{prepared_action_id}", response_model=PrepareResponse)
def get_prepared(case_id: str, prepared_action_id: str) -> PrepareResponse:
    _case_or_404(case_id)
    prepared = store.get(case_id, "prepared_action", prepared_action_id, PreparedAction)
    if prepared is None:
        raise HTTPException(404, "no such prepared action")
    decision = store.get(case_id, "decision", f"decision-{prepared.proposed_action_id}", Decision)
    return PrepareResponse(decision=decision, prepared=prepared)


# --- action endpoints: every one of these calls the unmodified core ---


@app.post("/api/cases/{case_id}/actions/prepare", response_model=PrepareResponse)
def prepare(case_id: str, body: PrepareRequest) -> PrepareResponse:
    _case_or_404(case_id)
    mandate = _current_mandate(case_id)
    _assert_principal(mandate, body.principal)
    observations = _load_observations(case_id)
    requirements = _load_requirements(case_id)
    files = _observation_files(case_id, observations)
    proposed_action = _proposed_action(case_id, body.allowed_device, body.destination)

    decision, prepared = prepare_evidence_package(
        proposed_action=proposed_action,
        mandate=mandate,
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device=body.allowed_device,
        destination=body.destination,
        now=now(),
        ttl=DEFAULT_PREPARED_ACTION_TTL,
    )
    _persist_prepare_result(case_id, proposed_action, decision, prepared)
    store.log_event(
        case_id,
        "prepared",
        f"Prepared '{proposed_action.operation}' on {body.allowed_device} — verdict {decision.verdict.value}",
        {"proposed_action_id": proposed_action.id, "reasons": decision.reasons},
        now().isoformat(),
    )
    return PrepareResponse(decision=decision, prepared=prepared)


@app.post("/api/cases/{case_id}/actions/propose-with-muse", response_model=MuseProposeResponse)
def propose_with_muse(case_id: str, body: MuseProposeRequest) -> MuseProposeResponse:
    """A real, billed call to Muse Spark (Standard mode) — a separate,
    explicitly-chosen endpoint, never triggered by `prepare` or any
    other flow. Muse proposes from the CURRENT live case state (see
    `_case_summaries`); its candidate is validated against
    `ProposedActionCandidate`'s schema by the adapter, then goes
    through the exact same `prepare_evidence_package` the hand-built
    path uses — Muse has no path to authority here, same as everywhere
    else in this codebase.

    The principal check runs BEFORE the billed call, not after — found
    by red-team review: checking identity after an expensive external
    call would still let an unauthorized caller trigger (and pay for)
    the call itself, even if its result were then discarded.
    """
    _case_or_404(case_id)
    mandate = _current_mandate(case_id)
    _assert_principal(mandate, body.principal)

    mission_summary, mandate_summary, case_summary = _case_summaries(case_id)
    try:
        candidate = propose_action(
            mission_summary=mission_summary,
            mandate_summary=mandate_summary,
            case_summary=case_summary,
        )
    except MuseAdapterError as exc:
        raise HTTPException(502, f"Muse call failed or returned an invalid response: {exc}")

    observations = _load_observations(case_id)
    requirements = _load_requirements(case_id)
    files = _observation_files(case_id, observations)
    proposed_action = ProposedAction(
        id=f"action-{uuid.uuid4().hex[:10]}",
        operation=candidate.operation,
        arguments={"device": candidate.allowed_device, "destination": candidate.destination},
        expected_effect=candidate.reasoning,
        mission_id=case_id,
    )

    decision, prepared = prepare_evidence_package(
        proposed_action=proposed_action,
        mandate=mandate,
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device=candidate.allowed_device,
        destination=candidate.destination,
        now=now(),
        ttl=DEFAULT_PREPARED_ACTION_TTL,
    )
    _persist_prepare_result(case_id, proposed_action, decision, prepared)
    store.log_event(
        case_id,
        "muse_proposed",
        f"Muse proposed '{candidate.operation}' on {candidate.allowed_device} — verdict {decision.verdict.value}",
        {
            "proposed_action_id": proposed_action.id,
            "muse_reasoning": candidate.reasoning,
            "reasons": decision.reasons,
        },
        now().isoformat(),
    )
    return MuseProposeResponse(
        muse_operation=candidate.operation,
        muse_allowed_device=candidate.allowed_device,
        muse_destination=candidate.destination,
        muse_reasoning=candidate.reasoning,
        decision=decision,
        prepared=prepared,
    )


@app.post("/api/cases/{case_id}/analyze-note", response_model=AnalyzeNoteResponse)
def analyze_note(case_id: str, body: AnalyzeNoteRequest) -> AnalyzeNoteResponse:
    """Laya as a typed semantic sensor — docs/levels.md invariant 2:
    informs what a human should check, never grants authority. This
    endpoint does not touch any EvidenceRequirement, TaskResponsibility,
    Decision, or PreparedAction — it has no path to do so. Runs locally
    (no billing), but returns 503 rather than crashing the request if
    the optional `laya` dependency isn't available — an absent optional
    component degrades this one feature, not the rest of the case.
    """
    _case_or_404(case_id)
    mandate = _current_mandate(case_id)
    _assert_principal(mandate, body.principal)

    try:
        signals = analyze_handoff_note(body.note_text)
    except LayaAdapterError as exc:
        raise HTTPException(503, f"Laya signal unavailable: {exc}")

    store.log_event(
        case_id,
        "laya_signal",
        (
            f"Laya analyzed a note: claims_independent_verification="
            f"{signals.claims_independent_verification:.2f}, "
            f"claims_task_complete={signals.claims_task_complete:.2f}, "
            f"urgency={signals.urgency:.2f}"
        ),
        {
            "note_text": body.note_text,
            "claims_independent_verification": signals.claims_independent_verification,
            "claims_task_complete": signals.claims_task_complete,
            "urgency": signals.urgency,
        },
        now().isoformat(),
    )
    return AnalyzeNoteResponse(
        claims_independent_verification=signals.claims_independent_verification,
        claims_task_complete=signals.claims_task_complete,
        urgency=signals.urgency,
    )


@app.post("/api/cases/{case_id}/actions/execute", response_model=ExecuteResponse)
def execute(case_id: str, body: ExecuteRequest) -> ExecuteResponse:
    _case_or_404(case_id)
    prepared = store.get(case_id, "prepared_action", body.prepared_action_id, PreparedAction)
    if prepared is None:
        raise HTTPException(404, "no such prepared action")
    proposed_action = store.get(case_id, "proposed_action", prepared.proposed_action_id, ProposedAction)
    decision = store.get(case_id, "decision", f"decision-{prepared.proposed_action_id}", Decision)
    if proposed_action is None or decision is None:
        raise HTTPException(409, "prepared action exists but its proposed_action/decision do not")

    # A recovered PreparedAction already decided which resource(s) to
    # exclude and why (prepared.excluded_resource_reasons) — the same
    # exclusion must still hold at execute time, or the revalidation
    # below would see the still-bad resource again and refuse the whole
    # action. Same caller contract documented in docs/levels.md's
    # Level 2 Cycle 3 section and exercised in tests/test_recovery.py.
    excluded_ids = {e.resource_id for e in prepared.excluded_resource_reasons}
    observations = [o for o in _load_observations(case_id) if o.id not in excluded_ids]
    requirements = [r for r in _load_requirements(case_id) if r.observation_id not in excluded_ids]
    files = _observation_files(case_id, observations)
    mandate = _current_mandate(case_id)
    _assert_principal(mandate, body.principal)
    nonce_claimed = store.claim_nonce(case_id, prepared.nonce, prepared.id, now().isoformat())
    consumed = set() if nonce_claimed else {prepared.nonce}
    out_dir = DATA_DIR / case_id / "packages" / prepared.id

    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=proposed_action,
        observations=observations,
        requirements=requirements,
        observation_files=files,
        current_mandate=mandate,
        consumed_nonces=consumed,
        out_dir=out_dir,
        now=now(),
    )
    store.put_execution_receipt(case_id, receipt, now().isoformat())
    store.log_event(
        case_id,
        "executed" if receipt.executed else "execution_blocked",
        receipt.observed_effect or "(no effect recorded)",
        {"prepared_action_id": prepared.id, "executed": receipt.executed},
        now().isoformat(),
    )

    manifest = None
    manifest_path = out_dir / "manifest.json"
    if receipt.executed and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    return ExecuteResponse(receipt=receipt, manifest=manifest)


@app.post("/api/cases/{case_id}/actions/recover", response_model=RecoverResponse)
def recover(case_id: str, body: RecoverRequest) -> RecoverResponse:
    _case_or_404(case_id)
    mandate = _current_mandate(case_id)
    _assert_principal(mandate, body.principal)
    observations = _load_observations(case_id)
    requirements = _load_requirements(case_id)
    files = _observation_files(case_id, observations)
    proposed_action = _proposed_action(case_id, body.allowed_device, body.destination)

    outcome = propose_recovery_route(
        proposed_action=proposed_action,
        mandate=mandate,
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device=body.allowed_device,
        destination=body.destination,
        now=now(),
    )
    if outcome.recovered_prepared is not None:
        _persist_prepare_result(case_id, proposed_action, outcome.recovered_decision, outcome.recovered_prepared)
    store.log_event(
        case_id,
        "recovery_proposed" if outcome.recovered_prepared else "recovery_closed",
        outcome.closed_reason or f"Recovered, excluding {', '.join(outcome.excluded_resources)}",
        {"excluded_resources": outcome.excluded_resources, "attempted": outcome.attempted},
        now().isoformat(),
    )
    return RecoverResponse(
        attempted=outcome.attempted,
        excluded_resources=outcome.excluded_resources,
        decision=outcome.recovered_decision,
        prepared=outcome.recovered_prepared,
        closed_reason=outcome.closed_reason,
    )


# --- dev-only endpoints: simulate the staleness Level 2 exists to
# catch, so the mechanism can be demonstrated from the UI. Gated behind
# KRAKADYL_ENABLE_DEV_ROUTES (default on, for local/demo convenience) —
# found by red-team review (docs/red-team-api-and-frontend.md): the
# comment here used to just ASSERT "a real deployment gates or removes
# this router" without the code actually providing a gate to use.
# Setting KRAKADYL_ENABLE_DEV_ROUTES=0 is that gate now. It is never a
# path an investigator would use on a real case.

dev_router = APIRouter()


@dev_router.post("/api/dev/cases/{case_id}/tamper")
def dev_tamper(case_id: str, body: TamperRequest) -> dict:
    _case_or_404(case_id)
    # Validated against the case's own known observation ids, not just
    # "a file happens to exist at this path" — found by red-team review:
    # observation_file_path() interpolates observation_id into a path
    # unsanitized, so a crafted id containing "../" resolves OUTSIDE the
    # case's data directory (confirmed by induction). Requiring the id to
    # be a real, already-known observation closes that off structurally,
    # rather than trying to blocklist "../" and similar patterns.
    known_ids = {o.id for o in _load_observations(case_id)}
    if body.observation_id not in known_ids:
        raise HTTPException(404, "no such observation in this case")
    path = observation_file_path(DATA_DIR, case_id, body.observation_id)
    path.write_bytes(b"TAMPERED: this no longer matches the acquired digest")
    store.log_event(
        case_id,
        "dev_tampered",
        f"[dev] {body.observation_id} was overwritten to simulate tampering",
        {"observation_id": body.observation_id},
        now().isoformat(),
    )
    return {"ok": True}


@dev_router.post("/api/dev/cases/{case_id}/revoke-mandate")
def dev_revoke_mandate(case_id: str, body: RevokeMandateRequest) -> dict:
    _case_or_404(case_id)
    current = _current_mandate(case_id)
    # model_copy(update=...) does NOT re-run validators — reconstructing
    # through the real constructor does, same discipline as everywhere
    # else a "changed" domain object gets built in this codebase.
    revoked = Mandate(
        **{
            **current.model_dump(),
            "revoked": True,
            "revoked_reason": body.reason,
            "revision": str(int(current.revision) + 1),
        }
    )
    store.put(case_id, "mandate", revoked, now().isoformat())
    store.log_event(
        case_id,
        "dev_mandate_revoked",
        f"[dev] mandate revoked: {body.reason}",
        {"revision": revoked.revision},
        now().isoformat(),
    )
    return {"ok": True}


@dev_router.post("/api/dev/cases/{case_id}/unresolve-hypothesis-requirement")
def dev_unresolve_requirement(case_id: str) -> dict:
    _case_or_404(case_id)
    req = store.get(case_id, "requirement", "req-timestamp-check", EvidenceRequirement)
    if req is None:
        raise HTTPException(404, "no such requirement")
    updated = EvidenceRequirement(
        **{
            **req.model_dump(),
            "resolved": False,
            "unresolvable": True,
            "unresolvable_reason": "device clock was never synced; timestamp comparison is meaningless",
        }
    )
    store.put(case_id, "requirement", updated, now().isoformat())
    store.log_event(
        case_id,
        "dev_requirement_unresolvable",
        "[dev] req-timestamp-check became unresolvable",
        {"requirement_id": updated.id},
        now().isoformat(),
    )
    return {"ok": True}


@dev_router.post("/api/dev/cases/{case_id}/reset")
def dev_reset(case_id: str) -> dict:
    store.reset_case(case_id)
    ensure_seeded(store, DATA_DIR)
    return {"ok": True}


DEV_ROUTES_ENABLED = os.environ.get("KRAKADYL_ENABLE_DEV_ROUTES", "1") != "0"
if DEV_ROUTES_ENABLED:
    app.include_router(dev_router)
