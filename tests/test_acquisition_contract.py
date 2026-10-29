from __future__ import annotations

import hashlib
from io import BytesIO
import time
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from krakadyl.core.acquisition import (
    AcquisitionAuthorization,
    AcquisitionCoordinator,
    AcquisitionNeedSnapshot,
    AcquisitionPhase,
    AcquisitionProposal,
    AcquisitionResult,
    AcquisitionWorkflow,
    AdapterAttempt,
    AdapterResponse,
    AggregateCeilings,
    AnnotationCandidate,
    AttemptState,
    RetentionDecision,
    ProcessingPlan,
    ProcessorRequest,
    ResourceUsage,
    AcquiredObservation,
    canonical_json_object,
    canonical_record_digest,
    verify_processor_request,
    AcquisitionOutcomeUnknown,
)

NOW = datetime(2026, 10, 28, 19, 0, tzinfo=timezone.utc)
RAW = b"synthetic source bytes"
MASK = b"synthetic candidate annotation"


def _usage(*, usd_micros=0, bytes_count=0, frames=0, duration_ms=1) -> ResourceUsage:
    return ResourceUsage(usd_micros=usd_micros, bytes=bytes_count, frames=frames, duration_ms=duration_ms)


def _proposal_and_authorization():
    need = AcquisitionNeedSnapshot(
        case_id="case-synthetic",
        requirement_id="need-clock-source",
        requirement_revision="3",
        hypothesis_ids=("hypothesis-a",),
        question="Do the synthetic source records have consistent timestamps?",
        answer_classes=("consistent", "inconsistent"),
        need_state_digest="a" * 64,
    )
    retention = RetentionDecision(
        case_id="case-synthetic",
        policy_id="fixture-retention",
        policy_version="1",
        data_categories=("synthetic-fixture",),
        destination="local-test-only",
        retention_seconds=3600,
        disposition="delete-after-test",
        decided_by="test-policy",
        valid_until=NOW + timedelta(hours=1),
    )
    plan = ProcessingPlan(
        case_id="case-synthetic",
        capability_id="synthetic-processor",
        capability_version="1",
        provider_id="test-provider",
        model_id="fixed-fixture",
        model_version="1",
        prompt="Return only a synthetic annotation candidate.",
        prompt_template_version="1",
        parameters_json=canonical_json_object({"max_items": 2, "strict": True}),
        authorized_source_id="fixture-source",
        input_transformation="identity-bytes",
        destination="local-test-only",
        usage_ceiling=_usage(usd_micros=0, bytes_count=1000, frames=0, duration_ms=1000),
        retention_policy_id=retention.policy_id,
        retention_policy_version=retention.policy_version,
    )
    proposal = AcquisitionProposal(
        case_id="case-synthetic",
        need=need,
        source_id="fixture-source",
        source_capability_version="1",
        capture_specification_json=canonical_json_object({"fixture": "clock-pair-a"}),
        source_usage_ceiling=_usage(usd_micros=0, bytes_count=1000, frames=0, duration_ms=1000),
        expected_outcomes=("consistent", "inconsistent"),
        mandate_id="synthetic-mandate",
        mandate_revision="4",
        ceilings=AggregateCeilings(
            per_requirement=_usage(usd_micros=0, bytes_count=2000, frames=0, duration_ms=2000),
            per_case_mandate=_usage(usd_micros=0, bytes_count=4000, frames=0, duration_ms=4000),
            deployment_account=_usage(usd_micros=0, bytes_count=8000, frames=0, duration_ms=8000),
        ),
        retention=retention,
        processing_plan=plan,
    )
    authorization = AcquisitionAuthorization(
        case_id=proposal.case_id,
        authorization_id="auth-synthetic-1",
        proposal_digest=canonical_record_digest(proposal),
        need_state_digest=need.need_state_digest,
        mandate_id=proposal.mandate_id,
        mandate_revision=proposal.mandate_revision,
        authorizer_identity="synthetic-human",
        authentication_method="test-only-authenticator",
        retention_policy_id=retention.policy_id,
        retention_policy_version=retention.policy_version,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )
    return proposal, authorization


class _FakeClock:
    def now(self):
        return NOW


class _MemoryGate:
    def __init__(self):
        self.used_authorizations = set()
        self.unknown_requirements = set()
        self.workflow_requirements = {}
        self.workflow_snapshots = {}
        self.attempts = {}
        self.completed = []
        self.phase_counts = {}
        self.failed_before_dispatch = []

    def create_workflow(self, proposal, authorization, credential_proof, *, now):
        if authorization.authorization_id in self.used_authorizations:
            raise ValueError("authorization replay")
        if authorization.proposal_digest != canonical_record_digest(proposal):
            raise ValueError("proposal changed after authorization")
        if (
            authorization.case_id != proposal.case_id
            or authorization.need_state_digest != proposal.need.need_state_digest
            or authorization.mandate_id != proposal.mandate_id
            or authorization.mandate_revision != proposal.mandate_revision
            or authorization.retention_policy_id != proposal.retention.policy_id
            or authorization.retention_policy_version != proposal.retention.policy_version
            or not authorization.authorizer_identity
            or not authorization.authentication_method
        ):
            raise ValueError("authorization scope does not match the proposal")
        requirement_key = (proposal.case_id, proposal.need.requirement_id)
        if requirement_key in self.unknown_requirements:
            raise ValueError("requirement has an unreconciled unknown attempt")
        if authorization.case_id != proposal.case_id or now >= authorization.expires_at:
            raise ValueError("authorization is invalid for this proposal")
        self.used_authorizations.add(authorization.authorization_id)
        workflow = AcquisitionWorkflow(
            case_id=proposal.case_id,
            workflow_id=f"workflow-{authorization.authorization_id}",
            unknown_lock_digest=hashlib.sha256(
                f"{proposal.case_id}:{proposal.need.requirement_id}".encode()
            ).hexdigest(),
            proposal_digest=authorization.proposal_digest,
            authorization_id=authorization.authorization_id,
            actor_identity=authorization.authorizer_identity,
            reservation_id=f"reservation-{authorization.authorization_id}",
            reserved_usage=proposal.ceilings.per_requirement,
            actual_usage=_usage(),
        )
        self.workflow_requirements[workflow.workflow_id] = requirement_key
        self.workflow_snapshots[workflow.workflow_id] = workflow
        return workflow

    def begin_phase(self, workflow, phase, request, retention, credential_proof, *, now):
        request_digest = canonical_record_digest(request)
        request_reference = f"sha256:{request_digest}"
        key = (workflow.workflow_id, phase)
        if self.phase_counts.get(key, 0):
            raise ValueError("phase replay")
        if phase == AcquisitionPhase.PROCESSOR_DERIVATION:
            source_attempts = [a for a in self.attempts.values() if a.workflow_id == workflow.workflow_id]
            if not any(a.phase == AcquisitionPhase.SOURCE_CAPTURE and a.state == AttemptState.COMPLETED for a in source_attempts):
                raise ValueError("processor phase is out of order")
        self.phase_counts[key] = 1
        attempt = AdapterAttempt(
            case_id=workflow.case_id,
            attempt_id=f"attempt-{len(self.attempts) + 1}",
            workflow_id=workflow.workflow_id,
            phase=phase,
            state=AttemptState.DISPATCH_INTENT,
            request_reference=request_reference,
            request_digest=request_digest,
            reservation_id=workflow.reservation_id,
            reserved_usage=workflow.reserved_usage,
            actual_usage=_usage(),
            retention_policy_id=retention.policy_id,
            retention_policy_version=retention.policy_version,
        )
        self.attempts[attempt.attempt_id] = attempt
        return attempt

    def complete_phase(self, attempt, actual_usage, result, *, now):
        self.completed.append((attempt.attempt_id, actual_usage))
        self.attempts[attempt.attempt_id] = attempt.model_copy(update={"state": AttemptState.COMPLETED})
        workflow = self.workflow_snapshots[attempt.workflow_id].model_copy(
            update={"current_phase": attempt.phase, "actual_usage": actual_usage}
        )
        self.workflow_snapshots[attempt.workflow_id] = workflow
        return self.workflow_snapshots[attempt.workflow_id]

    def mark_unknown(self, attempt, reason, *, now):
        self.unknown_requirements.add(self.workflow_requirements[attempt.workflow_id])
        self.attempts[attempt.attempt_id] = attempt.model_copy(
            update={"state": AttemptState.UNKNOWN_AFTER_DISPATCH, "outcome_reason": reason}
        )

    def abort_before_phase_intent(self, workflow_id, phase, reason, *, now):
        self.failed_before_dispatch.append((workflow_id, reason))

    def fail_attempt_before_dispatch(self, workflow_id, phase, request_digest, reason, *, now):
        self.failed_before_dispatch.append((workflow_id, reason))


class _MemoryArtifacts:
    def __init__(self, *, corrupt_after_write=False):
        self.contents = {}
        self.corrupt_after_write = corrupt_after_write
        self.requests = {}
        self.counter = 0

    def put_original(
        self, case_id, workflow_id, source_id, source_version, source_attempt_id, actor, content, retention
    ):
        digest = hashlib.sha256(content).hexdigest()
        reference = f"sha256:{digest}"
        self.contents[reference] = b"corrupt" if self.corrupt_after_write else content
        self.counter += 1
        return AcquiredObservation(
            case_id=case_id,
            observation_id=f"observation-{self.counter}",
            workflow_id=workflow_id,
            source_attempt_id=source_attempt_id,
            source_id=source_id,
            source_capability_version=source_version,
            artifact_reference=reference,
            digest=digest,
            byte_length=len(content),
            captured_at=NOW,
            actor=actor,
            retention_policy_id=retention.policy_id,
            retention_policy_version=retention.policy_version,
        )

    def read_verified(self, observation):
        content = self.contents[observation.artifact_reference]
        if hashlib.sha256(content).hexdigest() != observation.digest:
            raise ValueError("stored artifact failed read-time digest verification")
        return content

    def put_annotation(self, case_id, attempt_id, observation, request, response, retention):
        request_digest = canonical_record_digest(request)
        request_reference = f"sha256:{request_digest}"
        output_digest = hashlib.sha256(response).hexdigest()
        return AnnotationCandidate(
            case_id=case_id,
            annotation_id="annotation-1",
            observation_id=observation.observation_id,
            observation_digest=observation.digest,
            attempt_id=attempt_id,
            provider_id=request.provider_id,
            model_id=request.model_id,
            model_version=request.model_version,
            request_reference=request_reference,
            request_digest=request_digest,
            output_reference=f"sha256:{output_digest}",
            output_digest=output_digest,
            usage=_usage(bytes_count=len(response)),
            is_empty=not response,
            retention_policy_id=retention.policy_id,
            retention_policy_version=retention.policy_version,
        )


class _SyntheticSource:
    def __init__(self, payload=RAW, *, fail=False):
        self.payload = payload
        self.fail = fail
        self.calls = []

    def capture(self, request, attempt):
        self.calls.append((request, attempt))
        if self.fail:
            raise TimeoutError("synthetic timeout")
        return AdapterResponse(payload=BytesIO(self.payload), usage=_usage(bytes_count=len(self.payload)))


class _SyntheticProcessor:
    def __init__(self, payload=MASK):
        self.payload = payload
        self.calls = []

    def process(self, request, observation_bytes, attempt):
        self.calls.append((request, observation_bytes, attempt))
        return AdapterResponse(payload=BytesIO(self.payload), usage=_usage(bytes_count=len(self.payload)))


def _coordinator(gate=None, artifacts=None, source=None, processor=None):
    return AcquisitionCoordinator(
        gate=gate or _MemoryGate(),
        artifacts=artifacts or _MemoryArtifacts(),
        source=source or _SyntheticSource(),
        processor=processor if processor is not None else _SyntheticProcessor(),
        clock=_FakeClock(),
    )


def test_synthetic_workflow_keeps_capture_annotation_and_evaluation_separate():
    proposal, authorization = _proposal_and_authorization()
    gate = _MemoryGate()
    source = _SyntheticSource()
    processor = _SyntheticProcessor()

    result = _coordinator(gate=gate, source=source, processor=processor).acquire(proposal, authorization, "fixture-proof")

    assert isinstance(result, AcquisitionResult)
    assert result.observation.digest == hashlib.sha256(RAW).hexdigest()
    assert result.annotation is not None
    assert result.annotation.observation_digest == result.observation.digest
    assert result.evaluation is None
    assert len(source.calls) == 1
    assert len(processor.calls) == 1
    assert len(gate.completed) == 2
    assert len(gate.used_authorizations) == 1


def test_empty_processor_output_is_candidate_not_a_negative_evaluation():
    proposal, authorization = _proposal_and_authorization()
    result = _coordinator(processor=_SyntheticProcessor(payload=b"")).acquire(proposal, authorization, "fixture-proof")

    assert result.annotation is not None
    assert result.annotation.is_empty is True
    assert result.evaluation is None


def test_changed_proposal_after_authorization_is_rejected_before_capture():
    proposal, authorization = _proposal_and_authorization()
    changed_plan = proposal.processing_plan.model_copy(update={"model_id": "changed-after-approval"})
    changed = proposal.model_copy(update={"processing_plan": changed_plan})
    source = _SyntheticSource()

    with pytest.raises(ValueError, match="proposal changed after authorization"):
        _coordinator(source=source).acquire(changed, authorization, "fixture-proof")

    assert source.calls == []


def test_malformed_dispatch_result_is_closed_before_adapter_invocation():
    class _MalformedGate(_MemoryGate):
        def begin_phase(self, *args, **kwargs):
            return object()

    proposal, authorization = _proposal_and_authorization()
    gate = _MalformedGate()
    source = _SyntheticSource()

    with pytest.raises(ValueError, match="matching committed dispatch attempt"):
        _coordinator(gate=gate, source=source).acquire(proposal, authorization, "fixture-proof")

    assert source.calls == []
    assert gate.failed_before_dispatch == [
        ("workflow-auth-synthetic-1", "gate_returned_mismatched_attempt")
    ]


def test_unknown_source_outcome_blocks_new_grant_for_the_same_requirement():
    proposal, authorization = _proposal_and_authorization()
    gate = _MemoryGate()
    source = _SyntheticSource(fail=True)
    coordinator = _coordinator(gate=gate, source=source)

    with pytest.raises(AcquisitionOutcomeUnknown):
        coordinator.acquire(proposal, authorization, "fixture-proof")

    retry_authorization = authorization.model_copy(update={"authorization_id": "auth-synthetic-retry"})
    with pytest.raises(ValueError, match="unreconciled unknown attempt"):
        coordinator.acquire(proposal, retry_authorization, "fixture-proof")

    assert len(source.calls) == 1
    assert gate.attempts["attempt-1"].state == AttemptState.UNKNOWN_AFTER_DISPATCH


def test_oversized_stream_is_rejected_before_artifact_persistence_or_processing():
    proposal, authorization = _proposal_and_authorization()
    gate = _MemoryGate()
    artifacts = _MemoryArtifacts()
    processor = _SyntheticProcessor()
    source = _SyntheticSource(payload=b"x" * 1001)

    with pytest.raises(AcquisitionOutcomeUnknown, match="source_capture"):
        _coordinator(gate=gate, artifacts=artifacts, source=source, processor=processor).acquire(
            proposal, authorization, "fixture-proof"
        )

    assert artifacts.contents == {}
    assert processor.calls == []
    assert gate.attempts["attempt-1"].state == AttemptState.UNKNOWN_AFTER_DISPATCH


def test_resource_usage_rejects_boolean_counts_at_the_boundary():
    with pytest.raises(ValidationError):
        ResourceUsage(usd_micros=False, bytes=0, frames=0, duration_ms=0)


def test_need_hypothesis_ids_require_unique_canonical_order():
    proposal, _ = _proposal_and_authorization()
    raw = proposal.need.model_dump()
    raw["hypothesis_ids"] = ("hypothesis-z", "hypothesis-a")

    with pytest.raises(ValidationError, match="sorted and unique"):
        AcquisitionNeedSnapshot.model_validate(raw)


def test_unimplemented_input_transformation_is_rejected_before_workflow_creation():
    proposal, _ = _proposal_and_authorization()
    raw = proposal.model_dump()
    raw["processing_plan"]["input_transformation"] = "redact-metadata-v1"

    with pytest.raises(ValidationError, match="only supports the identity-bytes"):
        AcquisitionProposal.model_validate(raw)


def test_stream_deadline_failure_closes_the_adapter_stream():
    class _SlowStream:
        closed = False

        def read(self, size):
            time.sleep(0.005)
            return b"x"

        def close(self):
            self.closed = True

    stream = _SlowStream()
    response = AdapterResponse(payload=stream, usage=_usage(bytes_count=1, duration_ms=1))

    with pytest.raises(ValueError, match="duration ceiling"):
        AcquisitionCoordinator._collect_payload(response, _usage(bytes_count=10, duration_ms=1), started_at=time.monotonic())

    assert stream.closed is True


def test_read_time_digest_mismatch_blocks_processor_dispatch():
    proposal, authorization = _proposal_and_authorization()
    gate = _MemoryGate()
    processor = _SyntheticProcessor()

    with pytest.raises(ValueError, match="read-time digest verification"):
        _coordinator(
            gate=gate,
            artifacts=_MemoryArtifacts(corrupt_after_write=True),
            processor=processor,
        ).acquire(proposal, authorization, "fixture-proof")

    assert processor.calls == []
    assert list(gate.attempts) == ["attempt-1"]
    assert gate.attempts["attempt-1"].state == AttemptState.COMPLETED
    assert gate.failed_before_dispatch == [("workflow-auth-synthetic-1", "processor_input_verification_failed")]
    assert gate.unknown_requirements == set()


def test_processor_request_cannot_change_prompt_model_parameters_or_input():
    proposal, _ = _proposal_and_authorization()
    plan = proposal.processing_plan
    observation = AcquiredObservation(
        case_id=proposal.case_id,
        observation_id="observation-x",
        workflow_id="workflow-x",
        source_attempt_id="attempt-source-x",
        source_id=proposal.source_id,
        source_capability_version=proposal.source_capability_version,
        artifact_reference="sha256:" + "b" * 64,
        digest="b" * 64,
        byte_length=4,
        captured_at=NOW,
        actor="synthetic-human",
        retention_policy_id=proposal.retention.policy_id,
        retention_policy_version=proposal.retention.policy_version,
    )
    request = ProcessorRequest(
        case_id=plan.case_id,
        plan_digest=canonical_record_digest(plan),
        provider_id=plan.provider_id,
        model_id=plan.model_id,
        model_version=plan.model_version,
        prompt=plan.prompt,
        prompt_template_version=plan.prompt_template_version,
        parameters_json=plan.parameters_json,
        observation_id=observation.observation_id,
        observation_digest=observation.digest,
        source_id=observation.source_id,
        input_transformation=plan.input_transformation,
        destination=plan.destination,
        usage_ceiling=plan.usage_ceiling,
        retention_policy_id=plan.retention_policy_id,
        retention_policy_version=plan.retention_policy_version,
    )
    changed = request.model_copy(update={"prompt": "changed prompt"})

    with pytest.raises(ValueError, match="does not match the authorized processing plan"):
        verify_processor_request(plan, observation, changed)


def test_canonical_parameters_reject_floats_and_duplicate_json_keys():
    with pytest.raises(ValueError, match="float is not permitted"):
        canonical_json_object({"threshold": 0.5})

    proposal, _ = _proposal_and_authorization()
    with pytest.raises(ValidationError, match="duplicate JSON object key"):
        ProcessingPlan.model_validate(
            {
                **proposal.processing_plan.model_dump(),
                "parameters_json": '{"limit":1,"limit":2}',
            }
        )
