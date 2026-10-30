"""Recording an EvidenceEvaluation and the one requirement transition it may cause.

`docs/level3-acquisition-contracts.md` keeps three things apart: the
acquired bytes (custody/integrity), the derived annotation (an untrusted
candidate), and the inferential evaluation (an identified evaluator, a
named criterion, one categorical outcome). This module is the only place
an evaluation is written, and the only place it may move an
`EvidenceRequirement`. It never touches a `Hypothesis` — hypotheses are
re-reviewed by people (see `invalidation.find_hypotheses_needing_review`),
never flipped by an evaluation.

The transition reuses the claim/verification distinction the rest of
KRAKADYL already enforces, rather than inventing a parallel one:

- SUPPORTS by an evaluator independent of the acquisition actor (and of
  whoever earlier reported it done) -> requirement resolved,
  `VERIFIED_DONE`, linked to the evaluation id and observation digest.
- SUPPORTS by the acquisition actor themself -> `REPORTED_DONE` only:
  a claim, not a verification. It stays MISSING in evidence state and
  shows up in `find_urgent_discrepancies` like any other unverified claim.
- CONTRADICTS, NO_DISCRIMINATING_CHANGE, INSUFFICIENT_OR_INVALID -> the
  requirement does not change. The evaluation is recorded and visible;
  the next step (another authorized route, or an explicit abstention)
  is a human decision, never inferred from the outcome.

Everything happens in one SQLite transaction that re-reads the current
requirement and compares it with the revision the evaluator saw, so an
evaluation written against a requirement that changed underneath it is
refused instead of silently applied.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict

from krakadyl.core.acquisition import (
    AcquiredObservation,
    AcquisitionPhase,
    AcquisitionProposal,
    AcquisitionWorkflow,
    AdapterAttempt,
    AnnotationCandidate,
    EvaluationOutcome,
    EvidenceEvaluation,
    canonical_record_digest,
    requirement_revision_digest,
)
from krakadyl.core.models import EvidenceRequirement, TaskResponsibility, TaskStatus
from krakadyl.store import KrakadylStore


class EvaluationRejected(ValueError):
    pass


class AttemptView(BaseModel):
    model_config = ConfigDict(frozen=True)

    attempt: AdapterAttempt
    state: str


class AcquisitionRecordView(BaseModel):
    """Everything recorded about one workflow, read back from the gate's
    own tables — the UI renders this, it never recomputes it."""

    model_config = ConfigDict(frozen=True)

    workflow: AcquisitionWorkflow
    state: str
    requirement_id: str
    proposal: AcquisitionProposal
    attempts: list[AttemptView]
    observation: Optional[AcquiredObservation]
    annotation: Optional[AnnotationCandidate]
    evaluations: list[EvidenceEvaluation]
    created_at: str


def _utc_iso(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


def _load_requirement(connection: sqlite3.Connection, case_id: str, requirement_id: str) -> EvidenceRequirement:
    row = connection.execute(
        "SELECT json FROM objects WHERE case_id=? AND kind='requirement' AND obj_id=?",
        (case_id, requirement_id),
    ).fetchone()
    if row is None:
        raise EvaluationRejected("requirement does not exist in this case")
    return EvidenceRequirement.model_validate_json(row[0])


def _write_requirement(connection: sqlite3.Connection, case_id: str, requirement: EvidenceRequirement, now_iso: str) -> None:
    connection.execute(
        "UPDATE objects SET json=?, updated_at=? WHERE case_id=? AND kind='requirement' AND obj_id=?",
        (requirement.model_dump_json(), now_iso, case_id, requirement.id),
    )


def _log(connection: sqlite3.Connection, case_id: str, kind: str, summary: str, detail: dict, now_iso: str) -> None:
    connection.execute(
        "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
        (case_id, now_iso, kind, summary, json.dumps(detail, sort_keys=True)),
    )


def _phase_results(connection: sqlite3.Connection, workflow_id: str):
    rows = connection.execute(
        "SELECT phase, state, result_json FROM acquisition_attempts WHERE workflow_id=?",
        (workflow_id,),
    ).fetchall()
    observation = annotation = None
    for phase, state, result_json in rows:
        if result_json is None or state != "completed":
            continue
        if phase == AcquisitionPhase.SOURCE_CAPTURE.value:
            observation = AcquiredObservation.model_validate_json(result_json)
        elif phase == AcquisitionPhase.PROCESSOR_DERIVATION.value:
            annotation = AnnotationCandidate.model_validate_json(result_json)
    return observation, annotation


def _transition(
    requirement: EvidenceRequirement,
    evaluation: EvidenceEvaluation,
    acquisition_actor: str,
) -> tuple[EvidenceRequirement, str]:
    """Pure: the requirement after this evaluation, and a one-line account of why."""
    if evaluation.outcome != EvaluationOutcome.SUPPORTS_REQUIREMENT:
        return requirement, (
            f"outcome '{evaluation.outcome.value}' does not change the requirement; "
            "it stays open until another authorized route or an explicit abstention"
        )
    previous_claimant = requirement.responsibility.reported_done_by
    independent = evaluation.evaluator_identity not in {acquisition_actor, previous_claimant}
    base = requirement.responsibility.model_dump()
    if not independent:
        # An earlier claimant stays on record (red team F8): overwriting
        # them with the newer self-evaluator would erase who said it
        # first. The self-evaluation itself is kept in the evaluation
        # table and the activity log.
        responsibility = TaskResponsibility(**{
            **base,
            "status": TaskStatus.REPORTED_DONE,
            "reported_done_by": previous_claimant or evaluation.evaluator_identity,
            "reported_done_at": requirement.responsibility.reported_done_at or evaluation.evaluated_at,
        })
        updated = EvidenceRequirement(**{**requirement.model_dump(), "responsibility": responsibility.model_dump()})
        return updated, (
            "supported by the acquisition actor or the earlier claimant only — recorded as "
            "REPORTED_DONE; an independent evaluator is still required"
        )
    responsibility = TaskResponsibility(**{
        **base,
        "status": TaskStatus.VERIFIED_DONE,
        "reported_done_by": previous_claimant or acquisition_actor,
        "reported_done_at": requirement.responsibility.reported_done_at or evaluation.evaluated_at,
        "verified_by": evaluation.evaluator_identity,
        "verified_at": evaluation.evaluated_at,
        "verification_method": (
            f"independent-evaluation:{evaluation.criterion_id}@{evaluation.criterion_version}"
        ),
        "verified_against": (
            f"{evaluation.evaluation_id} over observation sha256:{evaluation.observation_digest}"
        ),
    })
    updated = EvidenceRequirement(**{
        **requirement.model_dump(),
        "resolved": True,
        "responsibility": responsibility.model_dump(),
    })
    return updated, "independently evaluated as supporting — requirement resolved and verified"


def record_evaluation(
    store: KrakadylStore,
    *,
    case_id: str,
    workflow_id: str,
    expected_requirement_revision: str,
    evaluator_identity: str,
    criterion_id: str,
    criterion_version: str,
    outcome: EvaluationOutcome,
    rationale: str,
    now: datetime,
    verify_artifacts: Callable[[AcquiredObservation, Optional[AnnotationCandidate]], None],
) -> tuple[EvidenceEvaluation, EvidenceRequirement]:
    """`evaluator_identity` must already be verified by the caller's
    credential check; this function never accepts an asserted name from
    request data on its own authority.

    `verify_artifacts` must re-hash the stored capture (and annotation,
    when there is one) and raise if either no longer matches — an
    evaluation is a use of those bytes, and the contract requires every
    use to verify them (red team F3). It runs inside the transaction,
    immediately before the evaluation is written."""
    now_iso = _utc_iso(now)

    def transition(connection: sqlite3.Connection):
        row = connection.execute(
            "SELECT case_id, requirement_id, state, workflow_json, proposal_json "
            "FROM acquisition_workflows WHERE workflow_id=?",
            (workflow_id,),
        ).fetchone()
        if row is None or row[0] != case_id:
            raise EvaluationRejected("acquisition workflow does not exist in this case")
        # 'failed' is evaluable when its capture completed (red team F6):
        # a reconciled processor phase must not throw away an already
        # preserved observation. 'active'/'unknown' never are.
        if row[2] not in ("completed", "failed"):
            raise EvaluationRejected(
                f"acquisition workflow is '{row[2]}' — its outcome is not settled, so there is nothing to evaluate yet"
            )
        workflow = AcquisitionWorkflow.model_validate_json(row[3])
        proposal = AcquisitionProposal.model_validate_json(row[4])
        observation, annotation = _phase_results(connection, workflow_id)
        if observation is None:
            raise EvaluationRejected("this acquisition recorded no observation to evaluate")
        requirement = _load_requirement(connection, case_id, row[1])
        if requirement_revision_digest(requirement) != expected_requirement_revision:
            raise EvaluationRejected("requirement changed since it was shown to the evaluator; reload and evaluate again")
        if requirement.resolved or requirement.unresolvable:
            raise EvaluationRejected("requirement is already resolved or closed as unresolvable")
        # Red team F1: the capture answers the question it was approved
        # for. A requirement reworded since then needs a new capture,
        # not a reinterpretation of an old one.
        if (
            requirement.discriminating_question != proposal.need.question
            or tuple(requirement.answer_classes) != proposal.need.answer_classes
        ):
            raise EvaluationRejected(
                "this capture was approved for a different question or answer classes than the requirement states now"
            )
        try:
            verify_artifacts(observation, annotation)
        except (OSError, ValueError) as exc:
            raise EvaluationRejected(
                "stored capture or annotation failed integrity verification; it cannot be evaluated"
            ) from exc

        evaluation = EvidenceEvaluation(
            case_id=case_id,
            evaluation_id=f"evaluation-{secrets.token_hex(8)}",
            requirement_id=requirement.id,
            observation_id=observation.observation_id,
            observation_digest=observation.digest,
            annotation_id=annotation.annotation_id if annotation else None,
            annotation_digest=annotation.output_digest if annotation else None,
            evaluator_identity=evaluator_identity,
            evaluator_type="human",
            criterion_id=criterion_id,
            criterion_version=criterion_version,
            outcome=outcome,
            rationale=rationale,
            evaluated_at=now,
        )
        try:
            connection.execute(
                "INSERT INTO acquisition_evaluations (evaluation_id, case_id, workflow_id, requirement_id, "
                "evaluator_identity, evaluation_json, evaluation_digest, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    evaluation.evaluation_id, case_id, workflow_id, requirement.id, evaluator_identity,
                    evaluation.model_dump_json(), canonical_record_digest(evaluation), now_iso,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise EvaluationRejected("this evaluator already recorded an evaluation for this acquisition") from exc
        updated, account = _transition(requirement, evaluation, workflow.actor_identity)
        if updated != requirement:
            _write_requirement(connection, case_id, updated, now_iso)
        _log(connection, case_id, "acquisition_evaluated",
             f"{evaluator_identity} evaluated {requirement.id}: {outcome.value} — {account}",
             {"evaluation_id": evaluation.evaluation_id, "workflow_id": workflow_id,
              "requirement_id": requirement.id, "outcome": outcome.value,
              "annotation_considered": annotation is not None}, now_iso)
        return evaluation, updated

    return store.atomic_write(transition)


def abstain_requirement(
    store: KrakadylStore,
    *,
    case_id: str,
    requirement_id: str,
    expected_requirement_revision: str,
    actor_identity: str,
    reason: str,
    now: datetime,
) -> EvidenceRequirement:
    """Close a requirement honestly as unresolvable — "this evidence is
    not available" — instead of forcing an answer. Refused while an
    acquisition for it is active or its outcome unknown: abstaining
    over a capture that may still land would hide that capture."""
    if not reason.strip():
        raise EvaluationRejected("an abstention needs a stated reason")
    now_iso = _utc_iso(now)

    def transition(connection: sqlite3.Connection) -> EvidenceRequirement:
        requirement = _load_requirement(connection, case_id, requirement_id)
        if requirement_revision_digest(requirement) != expected_requirement_revision:
            raise EvaluationRejected("requirement changed since it was shown; reload before abstaining")
        # Red team F7: declaring evidence unobtainable is the decision of
        # whoever is responsible for obtaining it.
        if actor_identity != requirement.responsibility.owner:
            raise EvaluationRejected(
                f"only the requirement owner ({requirement.responsibility.owner}) can close it as unresolvable"
            )
        if requirement.resolved or requirement.unresolvable:
            raise EvaluationRejected("requirement is already resolved or closed as unresolvable")
        if connection.execute(
            "SELECT 1 FROM acquisition_workflows WHERE case_id=? AND requirement_id=? AND state IN ('active', 'unknown')",
            (case_id, requirement_id),
        ).fetchone():
            raise EvaluationRejected("an acquisition for this requirement is active or has an unknown outcome")
        evaluations = [
            row[0] for row in connection.execute(
                "SELECT evaluation_id FROM acquisition_evaluations WHERE case_id=? AND requirement_id=? ORDER BY created_at",
                (case_id, requirement_id),
            ).fetchall()
        ]
        basis = f" (after evaluations: {', '.join(evaluations)})" if evaluations else ""
        updated = EvidenceRequirement(**{
            **requirement.model_dump(),
            "unresolvable": True,
            "unresolvable_reason": f"{reason.strip()} — closed by {actor_identity}{basis}",
        })
        _write_requirement(connection, case_id, updated, now_iso)
        _log(connection, case_id, "requirement_abstained",
             f"{actor_identity} closed {requirement_id} as unresolvable: {reason.strip()}",
             {"requirement_id": requirement_id, "evaluation_ids": evaluations}, now_iso)
        return updated

    return store.atomic_write(transition)


def acquisition_history(store: KrakadylStore, case_id: str) -> list[AcquisitionRecordView]:
    def read(connection: sqlite3.Connection) -> list[AcquisitionRecordView]:
        views = []
        workflows = connection.execute(
            "SELECT workflow_id, requirement_id, state, workflow_json, proposal_json, created_at "
            "FROM acquisition_workflows WHERE case_id=? ORDER BY created_at, rowid",
            (case_id,),
        ).fetchall()
        for workflow_id, requirement_id, state, workflow_json, proposal_json, created_at in workflows:
            attempts = [
                AttemptView(attempt=AdapterAttempt.model_validate_json(attempt_json), state=attempt_state)
                for attempt_json, attempt_state in connection.execute(
                    "SELECT attempt_json, state FROM acquisition_attempts WHERE workflow_id=? ORDER BY created_at, rowid",
                    (workflow_id,),
                ).fetchall()
            ]
            observation, annotation = _phase_results(connection, workflow_id)
            evaluations = [
                EvidenceEvaluation.model_validate_json(row[0])
                for row in connection.execute(
                    "SELECT evaluation_json FROM acquisition_evaluations WHERE workflow_id=? ORDER BY created_at, rowid",
                    (workflow_id,),
                ).fetchall()
            ]
            views.append(AcquisitionRecordView(
                workflow=AcquisitionWorkflow.model_validate_json(workflow_json),
                state=state,
                requirement_id=requirement_id,
                proposal=AcquisitionProposal.model_validate_json(proposal_json),
                attempts=attempts,
                observation=observation,
                annotation=annotation,
                evaluations=evaluations,
                created_at=created_at,
            ))
        return views

    return store.read_locked(read)
