"""SQLite admission and lifecycle gate for provider-neutral acquisition.

The injected policies are mandatory. SQLite provides local durability and
coordination, but is not an identity provider or a cross-host lock service.
See ADR-001 in `docs/sqlite-acquisition-gate-design.md`.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Protocol

from krakadyl.core.acquisition import (
    AcquisitionAuthorization,
    AuthorizationRevocation,
    AcquiredObservation,
    AdapterAttempt,
    AnnotationCandidate,
    AcquisitionNeedSnapshot,
    AcquisitionPhase,
    AcquisitionProposal,
    AcquisitionWorkflow,
    AttemptState,
    ProcessorRequest,
    ResourceUsage,
    RetentionDecision,
    SourceCaptureRequest,
    UnknownDisposition,
    UnknownResolution,
    canonical_record_digest,
    need_state_digest,
    processor_request_for,
    requirement_revision_digest,
    verify_processor_request,
)
from krakadyl.core.models import EvidenceRequirement, Hypothesis, Mandate
from krakadyl.core.receipt import canonical_bytes
from krakadyl.store import KrakadylStore


class AuthorizationVerifier(Protocol):
    def verify(self, proposal, authorization, proof, now: datetime) -> str: ...


class AcquisitionScopePolicy(Protocol):
    """Perform a bounded local check; authorization runs inside the write transaction."""

    def authorize(self, identity, mandate, proposal, phase, now: datetime) -> None: ...


class BudgetPolicy(Protocol):
    """Return a local immutable cap; this method runs inside a SQLite write transaction."""

    def cap(self, scope_type: str, scope_id: str) -> ResourceUsage: ...


class RetentionPolicyProvider(Protocol):
    """Return a bounded local decision; current policy is rechecked in the transaction."""

    def current(self, proposal, now: datetime) -> RetentionDecision: ...


class RecoveryQuiescenceVerifier(Protocol):
    """Verify quiescence evidence bound to the supplied dispatch generation."""

    def verify(self, proof: object, dispatch_generation: int, now: datetime) -> bool: ...


class SQLiteAcquisitionGate:
    def __init__(
        self,
        *,
        store: KrakadylStore,
        authorization_verifier: AuthorizationVerifier,
        scope_policy: AcquisitionScopePolicy,
        budget_policy: BudgetPolicy,
        retention_policy: RetentionPolicyProvider,
        unknown_resolution_verifier: object,
        revocation_verifier: object,
        recovery_quiescence_verifier: RecoveryQuiescenceVerifier,
        deployment_scope_id: str,
        recovery_stale_after_seconds: int,
    ):
        if not deployment_scope_id:
            raise ValueError("deployment budget scope must be configured")
        if isinstance(recovery_stale_after_seconds, bool) or recovery_stale_after_seconds < 1:
            raise ValueError("recovery age must be a positive number of seconds")
        required_methods = (
            (authorization_verifier, "verify"),
            (scope_policy, "authorize"),
            (budget_policy, "cap"),
            (retention_policy, "current"),
            (unknown_resolution_verifier, "verify"),
            (revocation_verifier, "verify"),
            (recovery_quiescence_verifier, "verify"),
        )
        if any(not callable(getattr(component, method, None)) for component, method in required_methods):
            raise TypeError("every authorization, scope, budget, retention, resolution, and revocation policy is required")
        self._store = store
        self._authorization_verifier = authorization_verifier
        self._scope_policy = scope_policy
        self._budget_policy = budget_policy
        self._retention_policy = retention_policy
        self._unknown_resolution_verifier = unknown_resolution_verifier
        self._revocation_verifier = revocation_verifier
        self._recovery_quiescence_verifier = recovery_quiescence_verifier
        self._deployment_scope_id = deployment_scope_id
        self._recovery_stale_after_seconds = recovery_stale_after_seconds

    def recovery_generation(self) -> int:
        row = self._store.read_locked(lambda connection: connection.execute(
            "SELECT dispatch_generation FROM acquisition_gate_state WHERE singleton=1"
        ).fetchone())
        if row is None:
            raise RuntimeError("acquisition dispatch generation is missing")
        return int(row[0])

    def create_workflow(
        self,
        proposal: AcquisitionProposal,
        authorization: AcquisitionAuthorization,
        credential_proof: object,
        *,
        now: datetime,
    ) -> AcquisitionWorkflow:
        _require_aware(now)
        identity = self._authorization_verifier.verify(
            proposal, authorization, credential_proof, now
        )
        retention = self._retention_policy.current(proposal, now)
        self._validate_grant(proposal, authorization, identity, retention, now)
        proposal_digest = canonical_record_digest(proposal)

        def transition(connection: sqlite3.Connection) -> AcquisitionWorkflow:
            mandate = self._load(
                connection, proposal.case_id, "mandate", proposal.mandate_id, Mandate
            )
            requirement = self._load(
                connection, proposal.case_id, "requirement", proposal.need.requirement_id,
                EvidenceRequirement,
            )
            linked_rows = connection.execute(
                "SELECT json FROM objects WHERE case_id=? AND kind='hypothesis'",
                (proposal.case_id,),
            ).fetchall()
            hypotheses = sorted(
                (
                    Hypothesis.model_validate_json(row[0])
                    for row in linked_rows
                    if Hypothesis.model_validate_json(row[0]).discriminating_requirement_id
                    == requirement.id
                ),
                key=lambda item: item.id,
            )
            self._validate_current_need(proposal.need, requirement, hypotheses)
            if mandate.revision != proposal.mandate_revision or not _mandate_is_current(mandate, now):
                raise ValueError("current mandate is revoked or differs from the approved revision")
            if self._retention_policy.current(proposal, now) != retention:
                raise ValueError("retention policy changed during workflow admission")
            mandate_digest = _mandate_digest(mandate)
            self._scope_policy.authorize(
                identity, mandate, proposal, AcquisitionPhase.SOURCE_CAPTURE, now
            )
            if connection.execute(
                "SELECT 1 FROM acquisition_revocations WHERE authorization_id=?",
                (authorization.authorization_id,),
            ).fetchone():
                raise ValueError("authorization has been revoked")

            total = self._phase_ceiling(proposal)
            scope_grants = (
                ("requirement", json.dumps([proposal.case_id, proposal.need.requirement_id], separators=(",", ":")), proposal.ceilings.per_requirement),
                ("case_mandate", json.dumps([proposal.case_id, proposal.mandate_id], separators=(",", ":")), proposal.ceilings.per_case_mandate),
                ("deployment", self._deployment_scope_id, proposal.ceilings.deployment_account),
            )
            for scope_type, scope_id, grant_cap in scope_grants:
                if not _within(total, grant_cap):
                    raise ValueError("phase ceilings exceed the approved aggregate grant ceiling")
                policy_cap = self._budget_policy.cap(scope_type, scope_id)
                if not _within(grant_cap, policy_cap):
                    raise ValueError("approved aggregate ceiling exceeds immutable budget policy")
                used = self._used(connection, scope_type, scope_id)
                if not _within(_add(used, total), _minimum(grant_cap, policy_cap)):
                    raise ValueError("acquisition budget is exhausted for a required scope")

            workflow_id = f"workflow-{secrets.token_hex(16)}"
            workflow = AcquisitionWorkflow(
                case_id=proposal.case_id,
                workflow_id=workflow_id,
                unknown_lock_digest=hashlib.sha256(
                    f"{proposal.case_id}:{proposal.need.requirement_id}".encode()
                ).hexdigest(),
                proposal_digest=proposal_digest,
                authorization_id=authorization.authorization_id,
                actor_identity=identity,
                reservation_id=f"reservation-{workflow_id}",
                reserved_usage=total,
                actual_usage=_zero(),
            )
            connection.execute(
                "INSERT INTO acquisition_workflows "
                "(workflow_id, case_id, requirement_id, authorization_id, proposal_json, authorization_json, mandate_digest, workflow_json, state, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
                (
                    workflow_id, proposal.case_id, proposal.need.requirement_id,
                    authorization.authorization_id, proposal.model_dump_json(),
                    authorization.model_dump_json(), mandate_digest,
                    workflow.model_dump_json(), _utc_iso(now),
                ),
            )
            for scope_type, scope_id, _ in scope_grants:
                connection.execute(
                    "INSERT INTO acquisition_reservations "
                    "(workflow_id, scope_type, scope_id, reserved_json, committed_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (workflow_id, scope_type, scope_id, total.model_dump_json(), _zero().model_dump_json()),
                )
            self._event(connection, workflow, "workflow_created", now, {
                "proposal_digest": proposal_digest,
                "requirement_id": proposal.need.requirement_id,
                "authorization_id": authorization.authorization_id,
            })
            return workflow

        try:
            return self._store.atomic_write(transition)
        except sqlite3.IntegrityError as exc:
            raise ValueError("authorization already used or requirement already has an active acquisition") from exc

    def begin_phase(
        self,
        workflow: AcquisitionWorkflow,
        phase: AcquisitionPhase,
        request,
        retention: RetentionDecision,
        credential_proof: object,
        *,
        now: datetime,
    ) -> AdapterAttempt:
        _require_aware(now)
        row = self._store.read_locked(lambda connection: connection.execute(
            "SELECT proposal_json, authorization_json FROM acquisition_workflows WHERE workflow_id=?",
            (workflow.workflow_id,),
        ).fetchone())
        if row is None or row[1] is None:
            raise ValueError("workflow or retained authorization is missing")
        proposal = AcquisitionProposal.model_validate_json(row[0])
        authorization = AcquisitionAuthorization.model_validate_json(row[1])
        identity = self._authorization_verifier.verify(
            proposal, authorization, credential_proof, now
        )
        current_retention = self._retention_policy.current(proposal, now)
        self._validate_grant(proposal, authorization, identity, current_retention, now)
        if retention != current_retention:
            raise ValueError("dispatch retention decision is stale")

        def transition(connection: sqlite3.Connection) -> AdapterAttempt:
            stored = connection.execute(
                "SELECT case_id, authorization_id, workflow_json, state, mandate_digest "
                "FROM acquisition_workflows WHERE workflow_id=?",
                (workflow.workflow_id,),
            ).fetchone()
            if stored is None or stored[3] != "active":
                raise ValueError("workflow is not active")
            persisted_workflow = AcquisitionWorkflow.model_validate_json(stored[2])
            if persisted_workflow != workflow:
                raise ValueError("workflow snapshot is stale")
            if stored[0] != proposal.case_id or stored[1] != authorization.authorization_id:
                raise ValueError("workflow does not match its retained proposal and grant")
            self._revalidate_current(
                connection, proposal, authorization, identity, phase, now, stored[4]
            )
            if connection.execute(
                "SELECT 1 FROM acquisition_revocations WHERE authorization_id=?",
                (authorization.authorization_id,),
            ).fetchone():
                raise ValueError("authorization has been revoked")

            previous = connection.execute(
                "SELECT phase, state, result_json FROM acquisition_attempts "
                "WHERE workflow_id=? ORDER BY created_at, rowid",
                (workflow.workflow_id,),
            ).fetchall()
            if phase == AcquisitionPhase.SOURCE_CAPTURE:
                if previous:
                    raise ValueError("source capture phase has already been attempted")
                expected_request = SourceCaptureRequest(
                    case_id=proposal.case_id,
                    proposal_digest=canonical_record_digest(proposal),
                    need_state_digest=proposal.need.need_state_digest,
                    source_id=proposal.source_id,
                    source_capability_version=proposal.source_capability_version,
                    capture_specification_json=proposal.capture_specification_json,
                    question=proposal.need.question,
                    retention_policy_id=retention.policy_id,
                    retention_policy_version=retention.policy_version,
                    usage_ceiling=proposal.source_usage_ceiling,
                )
                if request != expected_request:
                    raise ValueError("source request does not match the approved acquisition proposal")
                phase_ceiling = proposal.source_usage_ceiling
            else:
                if proposal.processing_plan is None or len(previous) != 1:
                    raise ValueError("processor phase is not authorized or is out of order")
                old_phase, old_state, result_json = previous[0]
                if old_phase != AcquisitionPhase.SOURCE_CAPTURE.value or old_state != AttemptState.COMPLETED.value or not result_json:
                    raise ValueError("processor phase requires a completed source observation")
                observation = AcquiredObservation.model_validate_json(result_json)
                expected_request = processor_request_for(proposal.processing_plan, observation)
                if not isinstance(request, ProcessorRequest):
                    raise ValueError("processor phase requires a typed processor request")
                verify_processor_request(proposal.processing_plan, observation, request)
                if request != expected_request:
                    raise ValueError("processor request differs from the authorized observation")
                phase_ceiling = proposal.processing_plan.usage_ceiling

            reservation_rows = connection.execute(
                "SELECT reserved_json FROM acquisition_reservations WHERE workflow_id=?",
                (workflow.workflow_id,),
            ).fetchall()
            if len(reservation_rows) != 3 or any(
                not _within(phase_ceiling, ResourceUsage.model_validate_json(row[0]))
                for row in reservation_rows
            ):
                raise ValueError("workflow is missing a complete phase budget reservation")

            digest = canonical_record_digest(request)
            attempt = AdapterAttempt(
                case_id=workflow.case_id,
                attempt_id=f"attempt-{secrets.token_hex(16)}",
                workflow_id=workflow.workflow_id,
                phase=phase,
                state=AttemptState.DISPATCH_INTENT,
                request_reference=f"sha256:{digest}",
                request_digest=digest,
                reservation_id=workflow.reservation_id,
                reserved_usage=phase_ceiling,
                actual_usage=_zero(),
                retention_policy_id=retention.policy_id,
                retention_policy_version=retention.policy_version,
            )
            connection.execute(
                "INSERT INTO acquisition_attempts "
                "(attempt_id, workflow_id, case_id, phase, state, request_reference, request_digest, attempt_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt.attempt_id, workflow.workflow_id, workflow.case_id, phase.value,
                    attempt.state.value, attempt.request_reference, digest,
                    attempt.model_dump_json(), _utc_iso(now),
                ),
            )
            changed = connection.execute(
                "UPDATE acquisition_gate_state SET dispatch_generation=dispatch_generation+1 WHERE singleton=1"
            ).rowcount
            if changed != 1:
                raise RuntimeError("acquisition dispatch generation is missing")
            expiry = now + timedelta(seconds=retention.retention_seconds)
            if retention.valid_until is not None:
                expiry = min(expiry, retention.valid_until)
            connection.execute(
                "INSERT INTO acquisition_requests "
                "(attempt_id, case_id, request_digest, request_json, retention_json, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    attempt.attempt_id, workflow.case_id, digest, request.model_dump_json(),
                    retention.model_dump_json(), _utc_iso(expiry),
                ),
            )
            updated = persisted_workflow.model_copy(update={"current_phase": phase})
            connection.execute(
                "UPDATE acquisition_workflows SET workflow_json=? WHERE workflow_id=?",
                (updated.model_dump_json(), workflow.workflow_id),
            )
            self._event(connection, updated, "dispatch_intent", now, {
                "attempt_id": attempt.attempt_id, "phase": phase.value, "request_digest": digest,
            })
            return attempt

        return self._store.atomic_write(transition)

    def _revalidate_current(
        self, connection, proposal, authorization, identity, phase, now, approved_mandate_digest
    ):
        mandate = self._load(connection, proposal.case_id, "mandate", proposal.mandate_id, Mandate)
        requirement = self._load(
            connection, proposal.case_id, "requirement", proposal.need.requirement_id,
            EvidenceRequirement,
        )
        rows = connection.execute(
            "SELECT json FROM objects WHERE case_id=? AND kind='hypothesis'",
            (proposal.case_id,),
        ).fetchall()
        hypotheses = sorted(
            (item for row in rows if (item := Hypothesis.model_validate_json(row[0])).discriminating_requirement_id == requirement.id),
            key=lambda item: item.id,
        )
        self._validate_current_need(proposal.need, requirement, hypotheses)
        if (
            mandate.revision != authorization.mandate_revision
            or not _mandate_is_current(mandate, now)
            or not approved_mandate_digest
            or _mandate_digest(mandate) != approved_mandate_digest
        ):
            raise ValueError("current mandate is revoked or differs from the grant")
        if self._retention_policy.current(proposal, now) != proposal.retention:
            raise ValueError("retention policy changed before phase dispatch")
        self._scope_policy.authorize(identity, mandate, proposal, phase, now)

    def complete_phase(
        self,
        attempt: AdapterAttempt,
        actual_usage: ResourceUsage,
        result: AcquiredObservation | AnnotationCandidate,
        *,
        provider_request_id: str | None = None,
        now: datetime,
    ) -> AcquisitionWorkflow:
        _require_aware(now)
        def transition(connection: sqlite3.Connection) -> AcquisitionWorkflow:
            row = connection.execute(
                "SELECT a.attempt_json, a.state, r.request_json, w.proposal_json, w.workflow_json "
                "FROM acquisition_attempts a "
                "LEFT JOIN acquisition_requests r USING(attempt_id) "
                "JOIN acquisition_workflows w USING(workflow_id) "
                "WHERE a.attempt_id=? AND a.workflow_id=? AND a.phase=? AND a.request_digest=?",
                (attempt.attempt_id, attempt.workflow_id, attempt.phase.value, attempt.request_digest),
            ).fetchone()
            if row is None or row[1] != AttemptState.DISPATCH_INTENT.value:
                raise ValueError("attempt is not at a durable dispatch intent")
            persisted_attempt = AdapterAttempt.model_validate_json(row[0])
            if persisted_attempt != attempt:
                raise ValueError("attempt snapshot does not match the durable dispatch intent")
            proposal = AcquisitionProposal.model_validate_json(row[3])
            workflow = AcquisitionWorkflow.model_validate_json(row[4])
            request_json = row[2]
            if attempt.phase == AcquisitionPhase.SOURCE_CAPTURE:
                if not isinstance(result, AcquiredObservation):
                    raise ValueError("source phase completion requires an acquired observation")
                valid_result = (
                    result.case_id == workflow.case_id
                    and result.workflow_id == workflow.workflow_id
                    and result.source_attempt_id == attempt.attempt_id
                    and result.source_id == proposal.source_id
                    and result.source_capability_version == proposal.source_capability_version
                    and result.actor == workflow.actor_identity
                    and result.retention_policy_id == attempt.retention_policy_id
                    and result.retention_policy_version == attempt.retention_policy_version
                )
            else:
                if not isinstance(result, AnnotationCandidate):
                    raise ValueError("processor phase completion requires an annotation candidate")
                if request_json is not None:
                    request = ProcessorRequest.model_validate_json(request_json)
                else:
                    source_result = connection.execute(
                        "SELECT result_json FROM acquisition_attempts WHERE workflow_id=? AND phase=?",
                        (workflow.workflow_id, AcquisitionPhase.SOURCE_CAPTURE.value),
                    ).fetchone()
                    if source_result is None or source_result[0] is None:
                        raise ValueError("processor input provenance is unavailable after request expiry")
                    observation = AcquiredObservation.model_validate_json(source_result[0])
                    request = processor_request_for(proposal.processing_plan, observation)
                    if canonical_record_digest(request) != attempt.request_digest:
                        raise ValueError("expired processor request cannot be reconstructed from its digest")
                valid_result = (
                    result.case_id == workflow.case_id
                    and result.attempt_id == attempt.attempt_id
                    and result.observation_id == request.observation_id
                    and result.observation_digest == request.observation_digest
                    and result.provider_id == request.provider_id
                    and result.model_id == request.model_id
                    and result.model_version == request.model_version
                    and result.request_digest == attempt.request_digest
                    and result.request_reference == attempt.request_reference
                    and result.retention_policy_id == attempt.retention_policy_id
                    and result.retention_policy_version == attempt.retention_policy_version
                )
            result_usage_valid = (
                not isinstance(result, AnnotationCandidate)
                or _within(result.usage, attempt.reserved_usage)
            )
            if not valid_result or not result_usage_valid or not _within(actual_usage, attempt.reserved_usage):
                raise ValueError("phase result provenance or usage exceeds its committed intent")

            updated_attempt = persisted_attempt.model_copy(
                update={
                    "state": AttemptState.COMPLETED,
                    "actual_usage": actual_usage,
                    "provider_request_id": provider_request_id,
                }
            )
            connection.execute(
                "UPDATE acquisition_attempts SET state=?, attempt_json=?, result_json=? WHERE attempt_id=?",
                (AttemptState.COMPLETED.value, updated_attempt.model_dump_json(), result.model_dump_json(), attempt.attempt_id),
            )
            reservations = connection.execute(
                "SELECT scope_type, scope_id, reserved_json, committed_json "
                "FROM acquisition_reservations WHERE workflow_id=?",
                (workflow.workflow_id,),
            ).fetchall()
            if len(reservations) != 3:
                raise ValueError("workflow is missing a complete budget ledger")
            for reservation in reservations:
                scope_type, scope_id, reserved_json, committed_json = reservation
                reserved = ResourceUsage.model_validate_json(reserved_json)
                committed = ResourceUsage.model_validate_json(committed_json)
                if not _within(attempt.reserved_usage, reserved):
                    raise ValueError("phase reservation exceeds the outstanding workflow reserve")
                connection.execute(
                    "UPDATE acquisition_reservations SET reserved_json=?, committed_json=? "
                    "WHERE workflow_id=? AND scope_type=? AND scope_id=?",
                    (
                        _subtract(reserved, attempt.reserved_usage).model_dump_json(),
                        _add(committed, attempt.reserved_usage).model_dump_json(),
                        workflow.workflow_id, scope_type, scope_id,
                    ),
                )
            complete = (
                attempt.phase == AcquisitionPhase.PROCESSOR_DERIVATION
                or proposal.processing_plan is None
            )
            actual_total = _add(workflow.actual_usage, actual_usage)
            updated_workflow = workflow.model_copy(update={
                "actual_usage": actual_total,
                "current_phase": attempt.phase,
                "unknown": False,
            })
            connection.execute(
                "UPDATE acquisition_workflows SET workflow_json=?, state=? WHERE workflow_id=?",
                (updated_workflow.model_dump_json(), "completed" if complete else "active", workflow.workflow_id),
            )
            self._event(connection, updated_workflow, "phase_completed", now, {
                "attempt_id": attempt.attempt_id,
                "phase": attempt.phase.value,
                "actual_usage": actual_usage.model_dump(mode="json"),
                "upper_bound_committed": attempt.reserved_usage.model_dump(mode="json"),
            })
            return updated_workflow

        return self._store.atomic_write(transition)

    def mark_unknown(
        self,
        attempt: AdapterAttempt,
        reason: str,
        *,
        provider_request_id: str | None = None,
        now: datetime,
    ) -> None:
        _require_aware(now)
        def transition(connection):
            row = connection.execute(
                "SELECT attempt_json, state FROM acquisition_attempts "
                "WHERE attempt_id=? AND workflow_id=? AND phase=? AND request_digest=?",
                (attempt.attempt_id, attempt.workflow_id, attempt.phase.value, attempt.request_digest),
            ).fetchone()
            if row is None or row[1] != AttemptState.DISPATCH_INTENT.value:
                raise ValueError("only a committed dispatch intent can become unknown")
            persisted = AdapterAttempt.model_validate_json(row[0])
            if persisted != attempt:
                raise ValueError("attempt snapshot does not match the durable dispatch intent")
            updated_attempt = persisted.model_copy(update={
                "state": AttemptState.UNKNOWN_AFTER_DISPATCH,
                "outcome_reason": reason[:512],
                "provider_request_id": provider_request_id,
            })
            connection.execute(
                "UPDATE acquisition_attempts SET state=?, attempt_json=? WHERE attempt_id=?",
                (updated_attempt.state.value, updated_attempt.model_dump_json(), attempt.attempt_id),
            )
            workflow = self._workflow(connection, attempt.workflow_id)
            updated_workflow = workflow.model_copy(update={"unknown": True})
            connection.execute(
                "UPDATE acquisition_workflows SET workflow_json=?, state='unknown' WHERE workflow_id=?",
                (updated_workflow.model_dump_json(), workflow.workflow_id),
            )
            self._event(connection, updated_workflow, "attempt_unknown", now, {
                "attempt_id": attempt.attempt_id, "phase": attempt.phase.value,
                "reason_type": reason[:512],
            })

        self._store.atomic_write(transition)

    def abort_before_phase_intent(
        self, workflow_id: str, phase: AcquisitionPhase, reason: str, *, now: datetime
    ) -> None:
        _require_aware(now)
        def transition(connection):
            workflow = self._workflow(connection, workflow_id)
            state = connection.execute(
                "SELECT state FROM acquisition_workflows WHERE workflow_id=?", (workflow_id,)
            ).fetchone()[0]
            if state != "active":
                raise ValueError("only an active workflow can be aborted before intent")
            attempts = connection.execute(
                "SELECT phase, state FROM acquisition_attempts WHERE workflow_id=?",
                (workflow_id,),
            ).fetchall()
            if any(item[0] == phase.value for item in attempts):
                raise ValueError("phase already has a durable attempt; pre-intent abort is unsafe")
            if phase == AcquisitionPhase.SOURCE_CAPTURE and attempts:
                raise ValueError("source phase is not the next workflow phase")
            if phase == AcquisitionPhase.PROCESSOR_DERIVATION and not any(
                item[0] == AcquisitionPhase.SOURCE_CAPTURE.value
                and item[1] == AttemptState.COMPLETED.value for item in attempts
            ):
                raise ValueError("processor phase cannot abort before source completion")
            self._release_reservations(connection, workflow_id)
            connection.execute(
                "UPDATE acquisition_workflows SET state='failed' WHERE workflow_id=?",
                (workflow_id,),
            )
            self._event(connection, workflow, "workflow_aborted_before_intent", now, {
                "phase": phase.value, "reason_type": reason[:512],
            })

        self._store.atomic_write(transition)

    def fail_attempt_before_dispatch(
        self,
        workflow_id: str,
        phase: AcquisitionPhase,
        request_digest: str,
        reason: str,
        *,
        now: datetime,
    ) -> None:
        _require_aware(now)
        def transition(connection):
            row = connection.execute(
                "SELECT attempt_id, attempt_json, state FROM acquisition_attempts "
                "WHERE workflow_id=? AND phase=? AND request_digest=?",
                (workflow_id, phase.value, request_digest),
            ).fetchone()
            if row is None or row[2] != AttemptState.DISPATCH_INTENT.value:
                raise ValueError("matching dispatch intent is absent or no longer pending")
            attempt = AdapterAttempt.model_validate_json(row[1]).model_copy(update={
                "state": AttemptState.FAILED_BEFORE_DISPATCH,
                "outcome_reason": reason[:512],
            })
            connection.execute(
                "UPDATE acquisition_attempts SET state=?, attempt_json=? WHERE attempt_id=?",
                (attempt.state.value, attempt.model_dump_json(), row[0]),
            )
            workflow = self._workflow(connection, workflow_id)
            self._release_reservations(connection, workflow_id)
            connection.execute(
                "UPDATE acquisition_workflows SET state='failed' WHERE workflow_id=?",
                (workflow_id,),
            )
            self._event(connection, workflow, "attempt_failed_before_dispatch", now, {
                "attempt_id": row[0], "phase": phase.value, "reason_type": reason[:512],
            })

        self._store.atomic_write(transition)

    def recover_interrupted_attempts(self, recovery_proof: object, *, now: datetime) -> int:
        _require_aware(now)
        dispatch_generation = self.recovery_generation()
        if not self._recovery_quiescence_verifier.verify(
            recovery_proof, dispatch_generation, now
        ):
            raise ValueError("recovery proof is invalid for the current dispatch generation")

        def transition(connection):
            generation_row = connection.execute(
                "SELECT dispatch_generation FROM acquisition_gate_state WHERE singleton=1"
            ).fetchone()
            if generation_row is None:
                raise RuntimeError("acquisition dispatch generation is missing")
            current_generation = int(generation_row[0])
            if current_generation != dispatch_generation:
                raise ValueError("recovery proof is stale after a new dispatch intent")
            rows = connection.execute(
                "SELECT attempt_id, workflow_id FROM acquisition_attempts WHERE state=?",
                (AttemptState.DISPATCH_INTENT.value,),
            ).fetchall()
            for attempt_id, workflow_id in rows:
                attempt_row = connection.execute(
                    "SELECT attempt_json FROM acquisition_attempts WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
                attempt = AdapterAttempt.model_validate_json(attempt_row[0]).model_copy(update={
                    "state": AttemptState.UNKNOWN_AFTER_DISPATCH,
                    "outcome_reason": "process_recovery_found_unresolved_dispatch_intent",
                })
                connection.execute(
                    "UPDATE acquisition_attempts SET state=?, attempt_json=? WHERE attempt_id=?",
                    (attempt.state.value, attempt.model_dump_json(), attempt_id),
                )
                workflow = self._workflow(connection, workflow_id)
                updated = workflow.model_copy(update={"unknown": True})
                connection.execute(
                    "UPDATE acquisition_workflows SET state='unknown', workflow_json=? WHERE workflow_id=?",
                    (updated.model_dump_json(), workflow_id),
                )
                self._event(connection, updated, "attempt_recovered_as_unknown", now, {
                    "attempt_id": attempt_id, "phase": attempt.phase.value,
                })
            stale_before = _utc_iso(now - timedelta(seconds=self._recovery_stale_after_seconds))
            abandoned = connection.execute(
                "SELECT workflow_id, workflow_json FROM acquisition_workflows "
                "WHERE state='active' AND created_at<=?",
                (stale_before,),
            ).fetchall()
            recovered = 0
            for workflow_id, workflow_json in abandoned:
                has_pending = connection.execute(
                    "SELECT 1 FROM acquisition_attempts WHERE workflow_id=? AND state=? LIMIT 1",
                    (workflow_id, AttemptState.DISPATCH_INTENT.value),
                ).fetchone()
                if has_pending:
                    continue
                workflow = AcquisitionWorkflow.model_validate_json(workflow_json)
                self._release_reservations(connection, workflow_id)
                connection.execute(
                    "UPDATE acquisition_workflows SET state='failed' WHERE workflow_id=?",
                    (workflow_id,),
                )
                self._event(connection, workflow, "workflow_recovered_before_next_intent", now, {})
                recovered += 1
            return len(rows) + recovered

        return self._store.atomic_write(transition)

    def reconcile_unknown(
        self,
        attempt_id: str,
        resolution: UnknownResolution,
        credential_proof: object,
        *,
        now: datetime,
    ) -> AcquisitionWorkflow:
        _require_aware(now)
        row = self._store.read_locked(lambda connection: connection.execute(
            "SELECT w.proposal_json, w.authorization_json FROM acquisition_attempts a "
            "JOIN acquisition_workflows w USING(workflow_id) WHERE a.attempt_id=?",
            (attempt_id,),
        ).fetchone())
        if row is None:
            raise ValueError("unknown attempt does not exist")
        proposal = AcquisitionProposal.model_validate_json(row[0])
        authorization = AcquisitionAuthorization.model_validate_json(row[1])
        identity = self._unknown_resolution_verifier.verify(
            resolution, authorization, credential_proof, now
        )
        if (
            resolution.attempt_id != attempt_id
            or resolution.case_id != proposal.case_id
            or identity != resolution.actor_identity
        ):
            raise ValueError("unknown resolution identity or scope is invalid")

        def transition(connection):
            row = connection.execute(
                "SELECT a.attempt_json, a.state, w.workflow_id, w.workflow_json "
                "FROM acquisition_attempts a JOIN acquisition_workflows w USING(workflow_id) "
                "WHERE a.attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None or row[1] != AttemptState.UNKNOWN_AFTER_DISPATCH.value:
                raise ValueError("attempt is not awaiting unknown-outcome reconciliation")
            attempt = AdapterAttempt.model_validate_json(row[0])
            workflow = AcquisitionWorkflow.model_validate_json(row[3])
            if resolution.workflow_id != workflow.workflow_id:
                raise ValueError("unknown resolution names a different workflow")
            if connection.execute(
                "SELECT 1 FROM acquisition_resolutions WHERE attempt_id=?", (attempt_id,)
            ).fetchone():
                raise ValueError("unknown attempt already has a resolution")
            charged = attempt.reserved_usage if resolution.disposition == UnknownDisposition.ACCEPTED_AS_UNKNOWN else _zero()
            reservations = connection.execute(
                "SELECT scope_type, scope_id, reserved_json, committed_json "
                "FROM acquisition_reservations WHERE workflow_id=?", (workflow.workflow_id,)
            ).fetchall()
            if len(reservations) != 3:
                raise ValueError("workflow is missing a complete budget ledger")
            for reservation in reservations:
                scope_type, scope_id, reserved_json, committed_json = reservation
                reserved = ResourceUsage.model_validate_json(reserved_json)
                committed = ResourceUsage.model_validate_json(committed_json)
                if not _within(charged, reserved):
                    raise ValueError("unknown phase reserve is not present in the ledger")
                connection.execute(
                    "UPDATE acquisition_reservations SET reserved_json=?, committed_json=? "
                    "WHERE workflow_id=? AND scope_type=? AND scope_id=?",
                    (_zero().model_dump_json(), _add(committed, charged).model_dump_json(),
                     workflow.workflow_id, scope_type, scope_id),
                )
            final_attempt_state = (
                AttemptState.RECONCILED_NOT_DISPATCHED
                if resolution.disposition == UnknownDisposition.CONFIRMED_NOT_DISPATCHED
                else AttemptState.CLOSED_AS_UNKNOWN
            )
            resolved_attempt = attempt.model_copy(update={"state": final_attempt_state})
            connection.execute(
                "UPDATE acquisition_attempts SET state=?, attempt_json=? WHERE attempt_id=?",
                (final_attempt_state.value, resolved_attempt.model_dump_json(), attempt_id),
            )
            connection.execute(
                "INSERT INTO acquisition_resolutions "
                "(resolution_id, attempt_id, case_id, resolution_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (resolution.resolution_id, attempt_id, resolution.case_id, resolution.model_dump_json(), _utc_iso(now)),
            )
            updated_workflow = workflow.model_copy(update={"unknown": False})
            connection.execute(
                "UPDATE acquisition_workflows SET state='failed', workflow_json=? WHERE workflow_id=?",
                (updated_workflow.model_dump_json(), workflow.workflow_id),
            )
            self._event(connection, updated_workflow, "unknown_outcome_reconciled", now, {
                "attempt_id": attempt_id, "disposition": resolution.disposition.value,
                "upper_bound_committed": charged.model_dump(mode="json"),
            })
            return updated_workflow

        return self._store.atomic_write(transition)

    def revoke_authorization(
        self,
        revocation: AuthorizationRevocation,
        credential_proof: object,
        *,
        now: datetime,
    ) -> None:
        _require_aware(now)
        identity = self._revocation_verifier.verify(revocation, credential_proof, now)
        if identity != revocation.actor_identity:
            raise ValueError("grant revocation identity is invalid")

        def transition(connection):
            connection.execute(
                "INSERT INTO acquisition_revocations "
                "(authorization_id, case_id, revocation_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    revocation.authorization_id, revocation.case_id,
                    revocation.model_dump_json(), _utc_iso(now),
                ),
            )
            rows = connection.execute(
                "SELECT workflow_json FROM acquisition_workflows WHERE authorization_id=?",
                (revocation.authorization_id,),
            ).fetchall()
            for (workflow_json,) in rows:
                workflow = AcquisitionWorkflow.model_validate_json(workflow_json)
                if workflow.case_id != revocation.case_id:
                    raise ValueError("revocation case does not match the grant")
                self._event(connection, workflow, "authorization_revoked", now, {
                    "authorization_id": revocation.authorization_id,
                    "revocation_id": revocation.revocation_id,
                })

        self._store.atomic_write(transition)

    def purge_expired_requests(self, *, now: datetime) -> int:
        _require_aware(now)
        return self._store.atomic_write(lambda connection: connection.execute(
            "DELETE FROM acquisition_requests WHERE expires_at<=?", (_utc_iso(now),)
        ).rowcount)

    @staticmethod
    def _workflow(connection, workflow_id):
        row = connection.execute(
            "SELECT workflow_json FROM acquisition_workflows WHERE workflow_id=?", (workflow_id,)
        ).fetchone()
        if row is None:
            raise ValueError("acquisition workflow does not exist")
        return AcquisitionWorkflow.model_validate_json(row[0])

    @staticmethod
    def _release_reservations(connection, workflow_id):
        changed = connection.execute(
            "UPDATE acquisition_reservations SET reserved_json=? WHERE workflow_id=?",
            (_zero().model_dump_json(), workflow_id),
        ).rowcount
        if changed != 3:
            raise ValueError("workflow is missing a complete budget ledger")

    @staticmethod
    def _load(connection, case_id, kind, object_id, model):
        row = connection.execute(
            "SELECT json FROM objects WHERE case_id=? AND kind=? AND obj_id=?",
            (case_id, kind, object_id),
        ).fetchone()
        if row is None:
            raise ValueError(f"current {kind} record is missing")
        return model.model_validate_json(row[0])

    @staticmethod
    def _validate_grant(proposal, authorization, identity, retention, now):
        if not identity or identity != authorization.authorizer_identity:
            raise ValueError("verified identity does not match the grant authorizer")
        if (
            authorization.case_id != proposal.case_id
            or authorization.proposal_digest != canonical_record_digest(proposal)
            or authorization.need_state_digest != proposal.need.need_state_digest
            or authorization.mandate_id != proposal.mandate_id
            or authorization.mandate_revision != proposal.mandate_revision
            or authorization.retention_policy_id != retention.policy_id
            or authorization.retention_policy_version != retention.policy_version
            or retention != proposal.retention
            or (retention.valid_until is not None and now >= retention.valid_until)
            or now < authorization.issued_at
            or now >= authorization.expires_at
        ):
            raise ValueError("authorization is invalid for the current proposal or policy")

    @staticmethod
    def _validate_current_need(need: AcquisitionNeedSnapshot, requirement, hypotheses):
        if requirement.resolved or requirement.unresolvable or requirement.blocked_by_authority:
            raise ValueError("requirement is resolved, unresolvable, or blocked by authority")
        ids = tuple(item.id for item in hypotheses)
        if ids != need.hypothesis_ids:
            raise ValueError("proposal does not name every current linked hypothesis in canonical order")
        revision = requirement_revision_digest(requirement)
        digest = need_state_digest(requirement, list(hypotheses))
        if need.requirement_revision != revision or need.need_state_digest != digest:
            raise ValueError("proposal need snapshot is stale")

    @staticmethod
    def _phase_ceiling(proposal):
        total = proposal.source_usage_ceiling
        if proposal.processing_plan is not None:
            total = _add(total, proposal.processing_plan.usage_ceiling)
        return total

    @staticmethod
    def _used(connection, scope_type, scope_id):
        rows = connection.execute(
            "SELECT reserved_json, committed_json FROM acquisition_reservations "
            "WHERE scope_type=? AND scope_id=?",
            (scope_type, scope_id),
        ).fetchall()
        total = _zero()
        for reserved, committed in rows:
            total = _add(total, ResourceUsage.model_validate_json(reserved))
            total = _add(total, ResourceUsage.model_validate_json(committed))
        return total

    @staticmethod
    def _event(connection, workflow, kind, now, detail):
        connection.execute(
            "INSERT INTO acquisition_events (case_id, workflow_id, ts, kind, detail_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (workflow.case_id, workflow.workflow_id, _utc_iso(now), kind, json.dumps(detail, sort_keys=True)),
        )


def _zero():
    return ResourceUsage(usd_micros=0, bytes=0, frames=0, duration_ms=0)


def _require_aware(now: datetime) -> None:
    if now.utcoffset() is None:
        raise ValueError("gate timestamps must include a timezone")


def _utc_iso(value: datetime) -> str:
    _require_aware(value)
    return value.astimezone(timezone.utc).isoformat()


def _mandate_is_current(mandate: Mandate, now: datetime) -> bool:
    if mandate.revoked or mandate.valid_from.utcoffset() is None:
        return False
    if now < mandate.valid_from:
        return False
    if mandate.valid_until is not None:
        if mandate.valid_until.utcoffset() is None or now >= mandate.valid_until:
            return False
    return True


def _mandate_digest(mandate: Mandate) -> str:
    return hashlib.sha256(canonical_bytes(mandate.model_dump(mode="json"))).hexdigest()


def _add(left: ResourceUsage, right: ResourceUsage) -> ResourceUsage:
    return ResourceUsage(**{
        key: getattr(left, key) + getattr(right, key)
        for key in ("usd_micros", "bytes", "frames", "duration_ms")
    })


def _subtract(left: ResourceUsage, right: ResourceUsage) -> ResourceUsage:
    if not _within(right, left):
        raise ValueError("cannot subtract more than the current resource value")
    return ResourceUsage(**{
        key: getattr(left, key) - getattr(right, key)
        for key in ("usd_micros", "bytes", "frames", "duration_ms")
    })


def _within(value: ResourceUsage, ceiling: ResourceUsage) -> bool:
    return all(
        getattr(value, key) <= getattr(ceiling, key)
        for key in ("usd_micros", "bytes", "frames", "duration_ms")
    )


def _minimum(left: ResourceUsage, right: ResourceUsage) -> ResourceUsage:
    return ResourceUsage(**{
        key: min(getattr(left, key), getattr(right, key))
        for key in ("usd_micros", "bytes", "frames", "duration_ms")
    })
