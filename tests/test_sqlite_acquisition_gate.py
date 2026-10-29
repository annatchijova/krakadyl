from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
import hashlib
import sqlite3
from threading import Barrier, Event

import pytest

from krakadyl.core.acquisition import (
    AdapterAttempt,
    AcquisitionPhase,
    AcquisitionProposal,
    ResourceUsage,
    SourceCaptureRequest,
    AcquiredObservation,
    AnnotationCandidate,
    AuthorizationRevocation,
    processor_request_for,
    UnknownDisposition,
    UnknownResolution,
    canonical_record_digest,
)
from krakadyl.core.models import EvidenceRequirement, Hypothesis, Mandate, TaskResponsibility
from krakadyl.core.receipt import canonical_bytes
from krakadyl.store import KrakadylStore
from test_acquisition_contract import NOW, _proposal_and_authorization, _usage


class _Verifier:
    def verify(self, proposal, authorization, proof, now):
        assert proof == "test-proof-do-not-persist"
        return "synthetic-human"


class _Scope:
    def authorize(self, identity, mandate, proposal, phase, now):
        assert identity == "synthetic-human"


class _Budgets:
    def __init__(self, deployment_bytes=1_000_000):
        self.deployment_bytes = deployment_bytes

    def cap(self, scope_type, scope_id):
        if scope_type == "deployment":
            return _usage(usd_micros=1_000_000, bytes_count=self.deployment_bytes, frames=1000, duration_ms=1_000_000)
        return _usage(usd_micros=1_000_000, bytes_count=1_000_000, frames=1000, duration_ms=1_000_000)


class _Retention:
    def current(self, proposal, now):
        return proposal.retention


class _ResolutionVerifier:
    def verify(self, resolution, authorization, proof, now):
        return resolution.actor_identity


class _RevocationVerifier:
    def verify(self, revocation, proof, now):
        return revocation.actor_identity


class _RecoveryVerifier:
    def verify(self, proof, dispatch_generation, now):
        return (
            isinstance(proof, dict)
            and proof.get("attestation") == "verified-quiescence"
            and proof.get("dispatch_generation") == dispatch_generation
        )


def _records():
    proposal, authorization = _proposal_and_authorization()
    requirement = EvidenceRequirement(
        id=proposal.need.requirement_id,
        predicate="synthetic timestamps discriminate the hypotheses",
        acceptable_source_class="synthetic test source",
        resolved=False,
        responsibility=TaskResponsibility(owner="synthetic-human", status="in_progress"),
    )
    hypothesis = Hypothesis(
        id=proposal.need.hypothesis_ids[0],
        explanation="Synthetic hypothesis",
        discriminating_requirement_id=requirement.id,
    )
    requirement_revision = hashlib.sha256(canonical_bytes({
        "digest_type": "acquisition_requirement_revision",
        "digest_version": 1,
        "requirement": requirement.model_dump(mode="json"),
    })).hexdigest()
    need_state_digest = hashlib.sha256(canonical_bytes({
        "digest_type": "acquisition_need_state",
        "digest_version": 1,
        "requirement": requirement.model_dump(mode="json"),
        "hypotheses": [hypothesis.model_dump(mode="json")],
    })).hexdigest()
    need = proposal.need.model_copy(update={
        "requirement_revision": requirement_revision,
        "need_state_digest": need_state_digest,
    })
    proposal = proposal.model_copy(update={"need": need})
    authorization = authorization.model_copy(update={
        "proposal_digest": canonical_record_digest(proposal),
        "need_state_digest": need_state_digest,
    })
    mandate = Mandate(
        id=proposal.mandate_id,
        issuer="synthetic-authority",
        principal="synthetic-human",
        resources=[proposal.source_id],
        operations=["capture"],
        destinations=[proposal.retention.destination],
        valid_from=NOW - timedelta(hours=1),
        valid_until=NOW + timedelta(hours=1),
        revision=proposal.mandate_revision,
    )
    return proposal, authorization, requirement, hypothesis, mandate


def _records_for_case(case_id):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    need = proposal.need.model_copy(update={"case_id": case_id})
    retention = proposal.retention.model_copy(update={"case_id": case_id})
    plan = proposal.processing_plan.model_copy(update={"case_id": case_id})
    ceilings = proposal.ceilings.model_copy(update={
        "deployment_account": _usage(usd_micros=0, bytes_count=3000, duration_ms=10_000)
    })
    proposal = proposal.model_copy(update={
        "case_id": case_id,
        "need": need,
        "retention": retention,
        "processing_plan": plan,
        "ceilings": ceilings,
    })
    authorization = authorization.model_copy(update={
        "case_id": case_id,
        "authorization_id": f"auth-{case_id}",
        "proposal_digest": canonical_record_digest(proposal),
    })
    return proposal, authorization, requirement, hypothesis, mandate


def _gate(store, budgets=None):
    from krakadyl.core.acquisition_store import SQLiteAcquisitionGate

    return SQLiteAcquisitionGate(
        store=store,
        authorization_verifier=_Verifier(),
        scope_policy=_Scope(),
        budget_policy=budgets or _Budgets(),
        retention_policy=_Retention(),
        unknown_resolution_verifier=_ResolutionVerifier(),
        revocation_verifier=_RevocationVerifier(),
        recovery_quiescence_verifier=_RecoveryVerifier(),
        deployment_scope_id="synthetic-deployment",
        recovery_stale_after_seconds=60,
    )


def _recovery_proof(gate):
    return {
        "attestation": "verified-quiescence",
        "dispatch_generation": gate.recovery_generation(),
    }


def test_two_connections_admit_the_same_authorization_once_and_never_persist_proof(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    stores = [KrakadylStore(tmp_path / "gate.db") for _ in range(2)]
    for store in stores:
        store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
        store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
        store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gates = [_gate(store) for store in stores]

    def attempt(index):
        try:
            return gates[index].create_workflow(
                proposal, authorization, "test-proof-do-not-persist", now=NOW
            )
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (0, 1)))

    assert sum(result is not None for result in results) == 1
    for store in stores:
        rows = store._conn.execute(
            "SELECT proposal_json, workflow_json FROM acquisition_workflows"
        ).fetchall()
        assert len(rows) == 1
        assert all("test-proof-do-not-persist" not in value for row in rows for value in row)
        assert store._conn.execute("SELECT COUNT(*) FROM acquisition_workflows").fetchone()[0] == 1
        store.close()


def test_distinct_cases_cannot_race_past_the_deployment_budget_cap(tmp_path):
    records = [_records_for_case("case-synthetic-a"), _records_for_case("case-synthetic-b")]
    stores = [KrakadylStore(tmp_path / "deployment-budget.db") for _ in range(2)]
    gates = []
    for store, (proposal, authorization, requirement, hypothesis, mandate) in zip(stores, records):
        store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
        store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
        store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
        gates.append(_gate(store, _Budgets(deployment_bytes=3000)))
    barrier = Barrier(2)

    def attempt(index):
        proposal, authorization, _, _, _ = records[index]
        barrier.wait()
        try:
            return gates[index].create_workflow(
                proposal, authorization, "test-proof-do-not-persist", now=NOW
            )
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (0, 1)))

    assert sum(result is not None for result in results) == 1
    deployment_usage = stores[0].read_locked(lambda connection: sum(
        ResourceUsage.model_validate_json(row[0]).bytes
        + ResourceUsage.model_validate_json(row[1]).bytes
        for row in connection.execute(
            "SELECT reserved_json, committed_json FROM acquisition_reservations "
            "WHERE scope_type='deployment' AND scope_id='synthetic-deployment'"
        ).fetchall()
    ))
    assert deployment_usage == 2000
    assert deployment_usage <= 3000
    for store in stores:
        store.close()


def test_request_and_dispatch_intent_roll_back_as_one_transaction(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    store = KrakadylStore(tmp_path / "gate.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    workflow = gate.create_workflow(proposal, authorization, "test-proof-do-not-persist", now=NOW)
    request = SourceCaptureRequest(
        case_id=proposal.case_id,
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=proposal.need.need_state_digest,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        capture_specification_json=proposal.capture_specification_json,
        question=proposal.need.question,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
        usage_ceiling=proposal.source_usage_ceiling,
    )
    store.read_locked(lambda connection: connection.execute(
        "CREATE TRIGGER reject_acquisition_request BEFORE INSERT ON acquisition_requests "
        "BEGIN SELECT RAISE(ABORT, 'injected request persistence failure'); END"
    ))

    with pytest.raises(sqlite3.IntegrityError, match="injected request persistence failure"):
        gate.begin_phase(
            workflow, AcquisitionPhase.SOURCE_CAPTURE, request, proposal.retention,
            "test-proof-do-not-persist", now=NOW,
        )

    counts = store.read_locked(lambda connection: (
        connection.execute("SELECT COUNT(*) FROM acquisition_attempts").fetchone()[0],
        connection.execute("SELECT COUNT(*) FROM acquisition_requests").fetchone()[0],
    ))
    assert counts == (0, 0)
    store.close()


def test_missing_budget_scope_fails_closed_before_dispatch(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    store = KrakadylStore(tmp_path / "missing-budget.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    workflow = gate.create_workflow(
        proposal, authorization, "test-proof-do-not-persist", now=NOW
    )
    request = SourceCaptureRequest(
        case_id=proposal.case_id,
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=proposal.need.need_state_digest,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        capture_specification_json=proposal.capture_specification_json,
        question=proposal.need.question,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
        usage_ceiling=proposal.source_usage_ceiling,
    )
    store.atomic_write(lambda connection: connection.execute(
        "DELETE FROM acquisition_reservations WHERE workflow_id=? AND scope_type='deployment'",
        (workflow.workflow_id,),
    ))

    with pytest.raises(ValueError, match="complete phase budget reservation"):
        gate.begin_phase(
            workflow, AcquisitionPhase.SOURCE_CAPTURE, request, proposal.retention,
            "test-proof-do-not-persist", now=NOW,
        )

    assert store.read_locked(lambda connection: connection.execute(
        "SELECT COUNT(*) FROM acquisition_attempts WHERE workflow_id=?",
        (workflow.workflow_id,),
    ).fetchone()[0]) == 0
    store.close()


def test_completed_source_commits_its_full_ceiling_even_when_meter_reports_zero(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    store = KrakadylStore(tmp_path / "gate.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    workflow = gate.create_workflow(proposal, authorization, "test-proof-do-not-persist", now=NOW)
    request = SourceCaptureRequest(
        case_id=proposal.case_id,
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=proposal.need.need_state_digest,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        capture_specification_json=proposal.capture_specification_json,
        question=proposal.need.question,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
        usage_ceiling=proposal.source_usage_ceiling,
    )
    attempt = gate.begin_phase(
        workflow, AcquisitionPhase.SOURCE_CAPTURE, request, proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )
    observation = AcquiredObservation(
        case_id=proposal.case_id,
        observation_id="observation-fixture",
        workflow_id=workflow.workflow_id,
        source_attempt_id=attempt.attempt_id,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        artifact_reference="sha256:" + "a" * 64,
        digest="a" * 64,
        byte_length=12,
        captured_at=NOW,
        actor=workflow.actor_identity,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
    )

    expiry = NOW + timedelta(seconds=proposal.retention.retention_seconds)
    offset_now = expiry.astimezone(timezone(timedelta(hours=5)))
    assert gate.purge_expired_requests(now=offset_now) == 1
    updated = gate.complete_phase(
        attempt, _usage(), observation,
        provider_request_id="provider-request-canary", now=offset_now,
    )

    assert updated.current_phase == AcquisitionPhase.SOURCE_CAPTURE
    persisted_attempt = store.read_locked(lambda connection: connection.execute(
        "SELECT attempt_json FROM acquisition_attempts WHERE attempt_id=?", (attempt.attempt_id,)
    ).fetchone()[0])
    assert AdapterAttempt.model_validate_json(persisted_attempt).provider_request_id == "provider-request-canary"
    reservation = store.read_locked(lambda connection: connection.execute(
        "SELECT reserved_json, committed_json FROM acquisition_reservations "
        "WHERE workflow_id=? AND scope_type='requirement'",
        (workflow.workflow_id,),
    ).fetchone())
    reserved, committed = map(ResourceUsage.model_validate_json, reservation)
    assert reserved.bytes == proposal.processing_plan.usage_ceiling.bytes
    assert committed.bytes == proposal.source_usage_ceiling.bytes
    assert committed.usd_micros == 0
    assert store.read_locked(lambda connection: connection.execute(
        "SELECT COUNT(*) FROM acquisition_attempts WHERE attempt_id=?", (attempt.attempt_id,)
    ).fetchone()[0]) == 1
    store.close()


def test_processor_phase_is_bound_to_the_completed_source_and_finishes_budget_ledger(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    store = KrakadylStore(tmp_path / "processor.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    workflow = gate.create_workflow(
        proposal, authorization, "test-proof-do-not-persist", now=NOW
    )
    source_request = SourceCaptureRequest(
        case_id=proposal.case_id,
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=proposal.need.need_state_digest,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        capture_specification_json=proposal.capture_specification_json,
        question=proposal.need.question,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
        usage_ceiling=proposal.source_usage_ceiling,
    )
    source_attempt = gate.begin_phase(
        workflow, AcquisitionPhase.SOURCE_CAPTURE, source_request, proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )
    observation = AcquiredObservation(
        case_id=proposal.case_id, observation_id="observation-processor",
        workflow_id=workflow.workflow_id, source_attempt_id=source_attempt.attempt_id,
        source_id=proposal.source_id, source_capability_version=proposal.source_capability_version,
        artifact_reference="sha256:" + "d" * 64, digest="d" * 64, byte_length=16,
        captured_at=NOW, actor=workflow.actor_identity,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
    )
    workflow = gate.complete_phase(source_attempt, _usage(bytes_count=16), observation, now=NOW)
    request = processor_request_for(proposal.processing_plan, observation)
    processor_attempt = gate.begin_phase(
        workflow, AcquisitionPhase.PROCESSOR_DERIVATION, request, proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )
    output_digest = "e" * 64
    annotation = AnnotationCandidate(
        case_id=proposal.case_id,
        annotation_id="annotation-processor",
        observation_id=observation.observation_id,
        observation_digest=observation.digest,
        attempt_id=processor_attempt.attempt_id,
        provider_id=request.provider_id,
        model_id=request.model_id,
        model_version=request.model_version,
        request_reference=processor_attempt.request_reference,
        request_digest=processor_attempt.request_digest,
        output_reference=f"sha256:{output_digest}",
        output_digest=output_digest,
        usage=_usage(bytes_count=4),
        is_empty=False,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
    )

    completed = gate.complete_phase(
        processor_attempt, _usage(bytes_count=4), annotation, now=NOW
    )

    assert completed.current_phase == AcquisitionPhase.PROCESSOR_DERIVATION
    state = store.read_locked(lambda connection: connection.execute(
        "SELECT state FROM acquisition_workflows WHERE workflow_id=?",
        (workflow.workflow_id,),
    ).fetchone()[0])
    assert state == "completed"
    ledger = store.read_locked(lambda connection: connection.execute(
        "SELECT reserved_json, committed_json FROM acquisition_reservations "
        "WHERE workflow_id=? AND scope_type='requirement'",
        (workflow.workflow_id,),
    ).fetchone())
    reserved, committed = map(ResourceUsage.model_validate_json, ledger)
    assert reserved.bytes == 0
    assert committed.bytes == (
        proposal.source_usage_ceiling.bytes + proposal.processing_plan.usage_ceiling.bytes
    )
    store.close()


@pytest.mark.parametrize(
    ("disposition", "expected_committed_bytes"),
    [
        (UnknownDisposition.CONFIRMED_NOT_DISPATCHED, 0),
        (UnknownDisposition.ACCEPTED_AS_UNKNOWN, 1000),
    ],
)
def test_unknown_attempt_survives_reopen_and_only_verified_resolution_releases_lock(
    tmp_path, disposition, expected_committed_bytes
):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    db_path = tmp_path / "gate.db"
    store = KrakadylStore(db_path)
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    workflow = gate.create_workflow(proposal, authorization, "test-proof-do-not-persist", now=NOW)
    request = SourceCaptureRequest(
        case_id=proposal.case_id,
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=proposal.need.need_state_digest,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        capture_specification_json=proposal.capture_specification_json,
        question=proposal.need.question,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
        usage_ceiling=proposal.source_usage_ceiling,
    )
    attempt = gate.begin_phase(
        workflow, AcquisitionPhase.SOURCE_CAPTURE, request, proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )
    gate.mark_unknown(
        attempt, "synthetic_timeout", provider_request_id="provider-request-unknown", now=NOW
    )
    persisted_attempt = store.read_locked(lambda connection: connection.execute(
        "SELECT attempt_json FROM acquisition_attempts WHERE attempt_id=?", (attempt.attempt_id,)
    ).fetchone()[0])
    assert AdapterAttempt.model_validate_json(persisted_attempt).provider_request_id == "provider-request-unknown"
    store.close()

    reopened = KrakadylStore(db_path)
    gate = _gate(reopened)
    retry_proposal = proposal.model_copy(update={
        "ceilings": proposal.ceilings.model_copy(update={
            "per_requirement": _usage(usd_micros=0, bytes_count=10_000, duration_ms=10_000),
            "per_case_mandate": _usage(usd_micros=0, bytes_count=10_000, duration_ms=10_000),
            "deployment_account": _usage(usd_micros=0, bytes_count=10_000, duration_ms=10_000),
        })
    })
    retry_authorization = authorization.model_copy(update={"authorization_id": "auth-synthetic-retry"})
    retry_authorization = retry_authorization.model_copy(update={
        "proposal_digest": canonical_record_digest(retry_proposal)
    })
    with pytest.raises(ValueError, match="already used or requirement"):
        gate.create_workflow(retry_proposal, retry_authorization, "test-proof-do-not-persist", now=NOW)

    resolution = UnknownResolution(
        case_id=proposal.case_id,
        resolution_id="resolution-fixture",
        workflow_id=workflow.workflow_id,
        attempt_id=attempt.attempt_id,
        disposition=disposition,
        actor_identity="synthetic-human",
        rationale="Synthetic transport log proves no dispatch occurred.",
        resolved_at=NOW,
    )
    gate.reconcile_unknown(
        attempt.attempt_id, resolution, "synthetic-resolution-proof", now=NOW
    )

    committed = reopened.read_locked(lambda connection: ResourceUsage.model_validate_json(
        connection.execute(
            "SELECT committed_json FROM acquisition_reservations "
            "WHERE workflow_id=? AND scope_type='requirement'",
            (workflow.workflow_id,),
        ).fetchone()[0]
    ))
    assert committed.bytes == expected_committed_bytes

    retry = gate.create_workflow(
        retry_proposal, retry_authorization, "test-proof-do-not-persist", now=NOW
    )
    assert retry.workflow_id != workflow.workflow_id
    reopened.close()


def test_abort_and_dispatch_intent_have_one_serialized_winner(tmp_path):
    for iteration in range(5):
        proposal, authorization, requirement, hypothesis, mandate = _records()
        stores = [KrakadylStore(tmp_path / f"race-{iteration}.db") for _ in range(2)]
        for store in stores:
            store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
            store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
            store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
        gates = [_gate(store) for store in stores]
        workflow = gates[0].create_workflow(
            proposal, authorization, "test-proof-do-not-persist", now=NOW
        )
        request = SourceCaptureRequest(
            case_id=proposal.case_id,
            proposal_digest=canonical_record_digest(proposal),
            need_state_digest=proposal.need.need_state_digest,
            source_id=proposal.source_id,
            source_capability_version=proposal.source_capability_version,
            capture_specification_json=proposal.capture_specification_json,
            question=proposal.need.question,
            retention_policy_id=proposal.retention.policy_id,
            retention_policy_version=proposal.retention.policy_version,
            usage_ceiling=proposal.source_usage_ceiling,
        )
        barrier = Barrier(2)

        def begin():
            barrier.wait()
            try:
                return gates[1].begin_phase(
                    workflow, AcquisitionPhase.SOURCE_CAPTURE, request,
                    proposal.retention, "test-proof-do-not-persist", now=NOW,
                )
            except ValueError:
                return None

        def abort():
            barrier.wait()
            try:
                gates[0].abort_before_phase_intent(
                    workflow.workflow_id, AcquisitionPhase.SOURCE_CAPTURE,
                    "synthetic_abort", now=NOW,
                )
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            begin_future = pool.submit(begin)
            abort_future = pool.submit(abort)
            attempt = begin_future.result()
            abort_won = abort_future.result()

        assert (attempt is not None) != abort_won
        state, attempts = stores[0].read_locked(lambda connection: (
            connection.execute(
                "SELECT state FROM acquisition_workflows WHERE workflow_id=?",
                (workflow.workflow_id,),
            ).fetchone()[0],
            connection.execute(
                "SELECT COUNT(*) FROM acquisition_attempts WHERE workflow_id=?",
                (workflow.workflow_id,),
            ).fetchone()[0],
        ))
        assert (state == "active" and attempts == 1) or (state == "failed" and attempts == 0)
        for store in stores:
            store.close()


def test_recovery_closes_stale_workflow_abandoned_before_first_dispatch(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    db_path = tmp_path / "abandoned.db"
    store = KrakadylStore(db_path)
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    abandoned = gate.create_workflow(
        proposal, authorization, "test-proof-do-not-persist", now=NOW
    )
    store.close()

    reopened = KrakadylStore(db_path)
    gate = _gate(reopened)
    assert gate.recover_interrupted_attempts(
        _recovery_proof(gate), now=NOW + timedelta(seconds=61)
    ) == 1
    retry_authorization = authorization.model_copy(update={"authorization_id": "auth-after-recovery"})
    retry = gate.create_workflow(
        proposal, retry_authorization, "test-proof-do-not-persist", now=NOW + timedelta(seconds=61)
    )
    assert retry.workflow_id != abandoned.workflow_id
    reopened.close()


def test_revocation_between_phases_denies_dispatch_and_preserves_prior_charge(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    store = KrakadylStore(tmp_path / "revocation.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    workflow = gate.create_workflow(
        proposal, authorization, "test-proof-do-not-persist", now=NOW
    )
    request = SourceCaptureRequest(
        case_id=proposal.case_id,
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=proposal.need.need_state_digest,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        capture_specification_json=proposal.capture_specification_json,
        question=proposal.need.question,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
        usage_ceiling=proposal.source_usage_ceiling,
    )
    attempt = gate.begin_phase(
        workflow, AcquisitionPhase.SOURCE_CAPTURE, request, proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )
    observation = AcquiredObservation(
        case_id=proposal.case_id, observation_id="observation-revoke",
        workflow_id=workflow.workflow_id, source_attempt_id=attempt.attempt_id,
        source_id=proposal.source_id, source_capability_version=proposal.source_capability_version,
        artifact_reference="sha256:" + "b" * 64, digest="b" * 64, byte_length=1,
        captured_at=NOW, actor=workflow.actor_identity,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
    )
    workflow = gate.complete_phase(attempt, _usage(), observation, now=NOW)
    gate.revoke_authorization(
        AuthorizationRevocation(
            case_id=proposal.case_id,
            authorization_id=authorization.authorization_id,
            revocation_id="revocation-fixture",
            actor_identity="synthetic-human",
            rationale="Synthetic revocation fixture.",
            revoked_at=NOW,
        ),
        "synthetic-revocation-proof",
        now=NOW,
    )
    processor_request = processor_request_for(proposal.processing_plan, observation)

    with pytest.raises(ValueError, match="authorization has been revoked"):
        gate.begin_phase(
            workflow, AcquisitionPhase.PROCESSOR_DERIVATION, processor_request,
            proposal.retention, "test-proof-do-not-persist", now=NOW,
        )
    gate.abort_before_phase_intent(
        workflow.workflow_id, AcquisitionPhase.PROCESSOR_DERIVATION,
        "authorization_revoked", now=NOW,
    )
    reserved, committed = store.read_locked(lambda connection: tuple(
        ResourceUsage.model_validate_json(row[index])
        for row in connection.execute(
            "SELECT reserved_json, committed_json FROM acquisition_reservations "
            "WHERE workflow_id=? AND scope_type='requirement'",
            (workflow.workflow_id,),
        ).fetchall()
        for index in (0, 1)
    ))
    assert reserved.bytes == 0
    assert committed.bytes == proposal.source_usage_ceiling.bytes
    store.close()


def test_gate_rejects_expired_mandate_and_retention_even_when_policies_allow(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    expired_mandate = mandate.model_copy(update={"valid_until": NOW - timedelta(seconds=1)})
    store = KrakadylStore(tmp_path / "expired-mandate.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", expired_mandate, NOW.isoformat())
    with pytest.raises(ValueError, match="mandate is revoked or differs"):
        _gate(store).create_workflow(
            proposal, authorization, "test-proof-do-not-persist", now=NOW
        )
    store.close()

    proposal, authorization, requirement, hypothesis, mandate = _records()
    expired_retention = proposal.retention.model_copy(update={"valid_until": NOW - timedelta(seconds=1)})
    proposal = proposal.model_copy(update={"retention": expired_retention})
    authorization = authorization.model_copy(update={
        "proposal_digest": canonical_record_digest(proposal)
    })
    store = KrakadylStore(tmp_path / "expired-retention.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    with pytest.raises(ValueError, match="invalid for the current proposal or policy"):
        _gate(store).create_workflow(
            proposal, authorization, "test-proof-do-not-persist", now=NOW
        )
    store.close()


def test_dispatch_rejects_same_revision_mandate_mutation_after_admission(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    store = KrakadylStore(tmp_path / "mandate-snapshot.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    workflow = gate.create_workflow(
        proposal, authorization, "test-proof-do-not-persist", now=NOW
    )
    changed_mandate = mandate.model_copy(update={"principal": "different-synthetic-human"})
    store.put(proposal.case_id, "mandate", changed_mandate, NOW.isoformat())
    request = SourceCaptureRequest(
        case_id=proposal.case_id,
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=proposal.need.need_state_digest,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        capture_specification_json=proposal.capture_specification_json,
        question=proposal.need.question,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
        usage_ceiling=proposal.source_usage_ceiling,
    )

    with pytest.raises(ValueError, match="current mandate is revoked or differs"):
        gate.begin_phase(
            workflow, AcquisitionPhase.SOURCE_CAPTURE, request, proposal.retention,
            "test-proof-do-not-persist", now=NOW,
        )

    states = store.read_locked(lambda connection: (
        connection.execute(
            "SELECT state FROM acquisition_workflows WHERE workflow_id=?",
            (workflow.workflow_id,),
        ).fetchone()[0],
        connection.execute(
            "SELECT count(*) FROM acquisition_attempts WHERE workflow_id=?",
            (workflow.workflow_id,),
        ).fetchone()[0],
    ))
    assert states == ("active", 0)
    store.close()


def test_recovery_rejects_quiescence_proof_stale_after_new_dispatch(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    store = KrakadylStore(tmp_path / "stale-recovery-proof.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    workflow = gate.create_workflow(
        proposal, authorization, "test-proof-do-not-persist", now=NOW
    )
    source_request = SourceCaptureRequest(
        case_id=proposal.case_id,
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=proposal.need.need_state_digest,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        capture_specification_json=proposal.capture_specification_json,
        question=proposal.need.question,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
        usage_ceiling=proposal.source_usage_ceiling,
    )
    source_attempt = gate.begin_phase(
        workflow, AcquisitionPhase.SOURCE_CAPTURE, source_request, proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )
    observation = AcquiredObservation(
        case_id=proposal.case_id, observation_id="observation-stale-proof",
        workflow_id=workflow.workflow_id, source_attempt_id=source_attempt.attempt_id,
        source_id=proposal.source_id, source_capability_version=proposal.source_capability_version,
        artifact_reference="sha256:" + "c" * 64, digest="c" * 64, byte_length=1,
        captured_at=NOW, actor=workflow.actor_identity,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
    )
    workflow = gate.complete_phase(source_attempt, _usage(), observation, now=NOW)
    stale_proof = _recovery_proof(gate)
    processor_request = processor_request_for(proposal.processing_plan, observation)
    processor_attempt = gate.begin_phase(
        workflow, AcquisitionPhase.PROCESSOR_DERIVATION, processor_request,
        proposal.retention, "test-proof-do-not-persist", now=NOW,
    )

    with pytest.raises(ValueError, match="recovery proof is invalid"):
        gate.recover_interrupted_attempts(stale_proof, now=NOW + timedelta(hours=1))

    state = store.read_locked(lambda connection: connection.execute(
        "SELECT state FROM acquisition_attempts WHERE attempt_id=?",
        (processor_attempt.attempt_id,),
    ).fetchone()[0])
    assert state == "dispatch_intent"
    assert gate.recovery_generation() == stale_proof["dispatch_generation"] + 1
    store.close()


def test_interrupted_dispatch_recovery_requires_verified_global_quiescence(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    store = KrakadylStore(tmp_path / "quiescence.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())
    gate = _gate(store)
    workflow = gate.create_workflow(
        proposal, authorization, "test-proof-do-not-persist", now=NOW
    )
    request = SourceCaptureRequest(
        case_id=proposal.case_id,
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=proposal.need.need_state_digest,
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        capture_specification_json=proposal.capture_specification_json,
        question=proposal.need.question,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
        usage_ceiling=proposal.source_usage_ceiling,
    )
    attempt = gate.begin_phase(
        workflow, AcquisitionPhase.SOURCE_CAPTURE, request, proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )

    with pytest.raises(ValueError, match="recovery proof is invalid"):
        gate.recover_interrupted_attempts("unverified", now=NOW + timedelta(hours=1))

    rows = store.read_locked(lambda connection: connection.execute(
        "SELECT state FROM acquisition_attempts WHERE attempt_id=?", (attempt.attempt_id,)
    ).fetchone())
    assert rows[0] == "dispatch_intent"
    assert gate.recover_interrupted_attempts(
        _recovery_proof(gate), now=NOW + timedelta(hours=1)
    ) == 1
    store.close()


def test_recovery_rejects_dispatch_committed_during_proof_verification(tmp_path):
    proof_checked = Event()
    release_proof = Event()
    dispatch_authorized = Event()

    class _BlockingRecoveryVerifier:
        def verify(self, proof, dispatch_generation, now):
            proof_checked.set()
            if not release_proof.wait(timeout=5):
                raise RuntimeError("test did not release recovery proof verifier")
            return (
                isinstance(proof, dict)
                and proof.get("attestation") == "verified-quiescence"
                and proof.get("dispatch_generation") == dispatch_generation
            )

    class _SignallingAuthorizationVerifier(_Verifier):
        def verify(self, proposal, authorization, proof, now):
            identity = super().verify(proposal, authorization, proof, now)
            dispatch_authorized.set()
            return identity

    db_path = tmp_path / "recovery-fence.db"
    stores = [KrakadylStore(db_path), KrakadylStore(db_path)]
    class _ConcurrentGateBudgets(_Budgets):
        def cap(self, scope_type, scope_id):
            return _usage(usd_micros=10**12, bytes_count=10**12, frames=10**9, duration_ms=10**12)

    budgets = _ConcurrentGateBudgets()
    gate_recovering = _gate(stores[0], budgets)
    gate_starting = _gate(stores[1], budgets)
    gate_starting._deployment_scope_id = "synthetic-deployment-second-worker"
    gate_starting._authorization_verifier = _SignallingAuthorizationVerifier()
    gate_recovering._recovery_quiescence_verifier = _BlockingRecoveryVerifier()

    prepared = []
    for case_id, gate, store in (
        ("case-recovery", gate_recovering, stores[0]),
        ("case-new-dispatch", gate_starting, stores[1]),
    ):
        proposal, authorization, requirement, hypothesis, mandate = _records_for_case(case_id)
        store.put(case_id, "requirement", requirement, NOW.isoformat())
        store.put(case_id, "hypothesis", hypothesis, NOW.isoformat())
        store.put(case_id, "mandate", mandate, NOW.isoformat())
        workflow = gate.create_workflow(
            proposal, authorization, "test-proof-do-not-persist", now=NOW
        )
        request = SourceCaptureRequest(
            case_id=proposal.case_id,
            proposal_digest=canonical_record_digest(proposal),
            need_state_digest=proposal.need.need_state_digest,
            source_id=proposal.source_id,
            source_capability_version=proposal.source_capability_version,
            capture_specification_json=proposal.capture_specification_json,
            question=proposal.need.question,
            retention_policy_id=proposal.retention.policy_id,
            retention_policy_version=proposal.retention.policy_version,
            usage_ceiling=proposal.source_usage_ceiling,
        )
        prepared.append((gate, proposal, workflow, request))

    old_gate, old_proposal, old_workflow, old_request = prepared[0]
    old_attempt = old_gate.begin_phase(
        old_workflow, AcquisitionPhase.SOURCE_CAPTURE, old_request, old_proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )
    new_gate, new_proposal, new_workflow, new_request = prepared[1]

    recovery_proof = _recovery_proof(old_gate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        recovery = pool.submit(
            old_gate.recover_interrupted_attempts,
            recovery_proof,
            now=NOW + timedelta(seconds=30),
        )
        assert proof_checked.wait(timeout=2)
        dispatch = pool.submit(
            new_gate.begin_phase,
            new_workflow,
            AcquisitionPhase.SOURCE_CAPTURE,
            new_request,
            new_proposal.retention,
            "test-proof-do-not-persist",
            now=NOW + timedelta(seconds=30),
        )
        assert dispatch_authorized.wait(timeout=2)
        new_attempt = dispatch.result(timeout=2)
        release_proof.set()
        with pytest.raises(ValueError, match="recovery proof is stale"):
            recovery.result(timeout=2)
        assert old_gate.recover_interrupted_attempts(
            _recovery_proof(old_gate), now=NOW + timedelta(seconds=30)
        ) == 2

    states = stores[0].read_locked(lambda connection: dict(connection.execute(
        "SELECT attempt_id, state FROM acquisition_attempts"
    ).fetchall()))
    assert states[old_attempt.attempt_id] == "unknown_after_dispatch"
    assert states[new_attempt.attempt_id] == "unknown_after_dispatch"
    for store in stores:
        store.close()


def test_recovery_lock_first_sweeps_only_dispatches_in_proof_generation(tmp_path):
    from concurrent.futures import TimeoutError

    lock_acquired = Event()
    release_recovery = Event()
    dispatch_authorized = Event()
    db_path = tmp_path / "recovery-lock-first.db"
    stores = [KrakadylStore(db_path), KrakadylStore(db_path)]

    class _ConcurrentGateBudgets(_Budgets):
        def cap(self, scope_type, scope_id):
            return _usage(usd_micros=10**12, bytes_count=10**12, frames=10**9, duration_ms=10**12)

    budgets = _ConcurrentGateBudgets()
    recovering_gate = _gate(stores[0], budgets)
    starting_gate = _gate(stores[1], budgets)
    starting_gate._deployment_scope_id = "synthetic-deployment-second-worker"

    class _SignallingAuthorizationVerifier(_Verifier):
        def verify(self, proposal, authorization, proof, now):
            identity = super().verify(proposal, authorization, proof, now)
            dispatch_authorized.set()
            return identity

    starting_gate._authorization_verifier = _SignallingAuthorizationVerifier()
    prepared = []
    for case_id, gate, store in (
        ("case-lock-recovery", recovering_gate, stores[0]),
        ("case-lock-new-dispatch", starting_gate, stores[1]),
    ):
        proposal, authorization, requirement, hypothesis, mandate = _records_for_case(case_id)
        store.put(case_id, "requirement", requirement, NOW.isoformat())
        store.put(case_id, "hypothesis", hypothesis, NOW.isoformat())
        store.put(case_id, "mandate", mandate, NOW.isoformat())
        workflow = gate.create_workflow(
            proposal, authorization, "test-proof-do-not-persist", now=NOW
        )
        request = SourceCaptureRequest(
            case_id=proposal.case_id,
            proposal_digest=canonical_record_digest(proposal),
            need_state_digest=proposal.need.need_state_digest,
            source_id=proposal.source_id,
            source_capability_version=proposal.source_capability_version,
            capture_specification_json=proposal.capture_specification_json,
            question=proposal.need.question,
            retention_policy_id=proposal.retention.policy_id,
            retention_policy_version=proposal.retention.policy_version,
            usage_ceiling=proposal.source_usage_ceiling,
        )
        prepared.append((gate, proposal, workflow, request))

    gate, proposal, workflow, source_request = prepared[0]
    source_attempt = gate.begin_phase(
        workflow, AcquisitionPhase.SOURCE_CAPTURE, source_request, proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )
    observation = AcquiredObservation(
        case_id=proposal.case_id, observation_id="observation-lock-first",
        workflow_id=workflow.workflow_id, source_attempt_id=source_attempt.attempt_id,
        source_id=proposal.source_id, source_capability_version=proposal.source_capability_version,
        artifact_reference="sha256:" + "d" * 64, digest="d" * 64, byte_length=1,
        captured_at=NOW, actor=workflow.actor_identity,
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
    )
    workflow = gate.complete_phase(source_attempt, _usage(), observation, now=NOW)
    processor_attempt = gate.begin_phase(
        workflow, AcquisitionPhase.PROCESSOR_DERIVATION,
        processor_request_for(proposal.processing_plan, observation), proposal.retention,
        "test-proof-do-not-persist", now=NOW,
    )
    proof = _recovery_proof(recovering_gate)
    original_atomic_write = stores[0].atomic_write

    def pause_after_lock(operation):
        def paused(connection):
            lock_acquired.set()
            if not release_recovery.wait(timeout=5):
                raise RuntimeError("test did not release recovery transaction")
            return operation(connection)

        return original_atomic_write(paused)

    stores[0].atomic_write = pause_after_lock
    _, new_proposal, new_workflow, new_request = prepared[1]

    with ThreadPoolExecutor(max_workers=2) as pool:
        recovery = pool.submit(
            recovering_gate.recover_interrupted_attempts,
            proof,
            now=NOW + timedelta(seconds=30),
        )
        assert lock_acquired.wait(timeout=2)
        dispatch = pool.submit(
            starting_gate.begin_phase,
            new_workflow,
            AcquisitionPhase.SOURCE_CAPTURE,
            new_request,
            new_proposal.retention,
            "test-proof-do-not-persist",
            now=NOW + timedelta(seconds=30),
        )
        assert dispatch_authorized.wait(timeout=2)
        with pytest.raises(TimeoutError):
            dispatch.result(timeout=0.1)
        release_recovery.set()
        assert recovery.result(timeout=2) == 1
        new_attempt = dispatch.result(timeout=2)

    states = stores[0].read_locked(lambda connection: dict(connection.execute(
        "SELECT attempt_id, state FROM acquisition_attempts"
    ).fetchall()))
    assert states[processor_attempt.attempt_id] == "unknown_after_dispatch"
    assert states[new_attempt.attempt_id] == "dispatch_intent"
    for store in stores:
        store.close()
