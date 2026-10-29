"""Provider-neutral contracts for authorized evidence acquisition.

This module defines data and ports only. It does not provide a production
authorization gate, budget ledger, artifact store, source, processor, or API
route; callers cannot obtain an acquisition path by importing these types.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from krakadyl.core.receipt import canonical_bytes

MAX_STRUCTURED_INPUT_BYTES = 65_536
MAX_STRUCTURED_DEPTH = 32
MAX_STRUCTURED_NODES = 4_096


def _reject_floats(value: Any, path: str = "record") -> None:
    pending = [(value, path, 0)]
    nodes = 0
    while pending:
        current, current_path, depth = pending.pop()
        nodes += 1
        if nodes > MAX_STRUCTURED_NODES or depth > MAX_STRUCTURED_DEPTH:
            raise ValueError("structured acquisition input exceeds its depth or node limit")
        if isinstance(current, float):
            raise ValueError(f"float is not permitted in acquisition record at {current_path}")
        if isinstance(current, dict):
            pending.extend((nested, f"{current_path}.{key}", depth + 1) for key, nested in current.items())
        elif isinstance(current, (list, tuple)):
            pending.extend((nested, f"{current_path}[{index}]", depth + 1) for index, nested in enumerate(current))


def canonical_json_object(value: dict[str, Any]) -> str:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise TypeError("canonical JSON value must be an object with string keys")
    _reject_floats(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_STRUCTURED_INPUT_BYTES:
        raise ValueError("canonical acquisition JSON exceeds its byte limit")
    return encoded


def _validate_canonical_json_object(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_STRUCTURED_INPUT_BYTES:
        raise ValueError("canonical acquisition JSON exceeds its byte limit")
    def reject_number(_: str) -> Any:
        raise ValueError("non-integer numeric values are not permitted")

    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, nested in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key}")
            result[key] = nested
        return result

    try:
        decoded = json.loads(
            value,
            parse_float=reject_number,
            parse_constant=reject_number,
            object_pairs_hook=unique_keys,
        )
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("record field must contain valid canonical JSON") from exc
    _reject_floats(decoded)
    if not isinstance(decoded, dict) or canonical_json_object(decoded) != value:
        raise ValueError("record field must be a canonical JSON object")
    return value


class AcquisitionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1

    @model_validator(mode="before")
    @classmethod
    def _reject_float_values(cls, value: Any) -> Any:
        _reject_floats(value)
        return value


class AcquisitionPhase(str, Enum):
    SOURCE_CAPTURE = "source_capture"
    PROCESSOR_DERIVATION = "processor_derivation"


class AttemptState(str, Enum):
    RESERVED = "reserved"
    DISPATCH_INTENT = "dispatch_intent"
    COMPLETED = "completed"
    FAILED_BEFORE_DISPATCH = "failed_before_dispatch"
    UNKNOWN_AFTER_DISPATCH = "unknown_after_dispatch"
    RECONCILED_NOT_DISPATCHED = "reconciled_not_dispatched"
    CLOSED_AS_UNKNOWN = "closed_as_unknown"


class UnknownDisposition(str, Enum):
    CONFIRMED_NOT_DISPATCHED = "confirmed_not_dispatched"
    ACCEPTED_AS_UNKNOWN = "accepted_as_unknown"


class EvaluationOutcome(str, Enum):
    SUPPORTS_REQUIREMENT = "supports_requirement"
    CONTRADICTS_REQUIREMENT = "contradicts_requirement"
    NO_DISCRIMINATING_CHANGE = "no_discriminating_change"
    INSUFFICIENT_OR_INVALID = "insufficient_or_invalid"


class ResourceUsage(AcquisitionRecord):
    usd_micros: int = Field(strict=True, ge=0)
    bytes: int = Field(strict=True, ge=0)
    frames: int = Field(strict=True, ge=0)
    duration_ms: int = Field(strict=True, ge=0)


class AggregateCeilings(AcquisitionRecord):
    per_requirement: ResourceUsage
    per_case_mandate: ResourceUsage
    deployment_account: ResourceUsage


class RetentionDecision(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    data_categories: tuple[str, ...] = Field(min_length=1)
    destination: str = Field(min_length=1)
    retention_seconds: int = Field(strict=True, gt=0)
    disposition: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)
    valid_until: datetime | None = None

    @field_validator("valid_until")
    @classmethod
    def _valid_until_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("retention decision expiry must include a timezone")
        return value


class AcquisitionNeedSnapshot(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    requirement_revision: str = Field(min_length=1)
    hypothesis_ids: tuple[str, ...] = Field(min_length=1)
    question: str = Field(min_length=1, max_length=16_384)
    answer_classes: tuple[str, ...] = Field(min_length=2)
    need_state_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _answer_classes_are_unique(self) -> AcquisitionNeedSnapshot:
        if len(set(self.answer_classes)) != len(self.answer_classes):
            raise ValueError("answer classes must be unique")
        if len(set(self.hypothesis_ids)) != len(self.hypothesis_ids) or tuple(sorted(self.hypothesis_ids)) != self.hypothesis_ids:
            raise ValueError("hypothesis IDs must be sorted and unique")
        return self


class ProcessingPlan(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    capability_version: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=16_384)
    prompt_template_version: str = Field(min_length=1)
    parameters_json: str = Field(min_length=2, max_length=MAX_STRUCTURED_INPUT_BYTES)
    authorized_source_id: str = Field(min_length=1)
    input_transformation: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    usage_ceiling: ResourceUsage
    retention_policy_id: str = Field(min_length=1)
    retention_policy_version: str = Field(min_length=1)

    @field_validator("parameters_json")
    @classmethod
    def _parameters_are_canonical(cls, value: str) -> str:
        return _validate_canonical_json_object(value)


class AcquisitionProposal(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    need: AcquisitionNeedSnapshot
    source_id: str = Field(min_length=1)
    source_capability_version: str = Field(min_length=1)
    capture_specification_json: str = Field(min_length=2, max_length=MAX_STRUCTURED_INPUT_BYTES)
    source_usage_ceiling: ResourceUsage
    expected_outcomes: tuple[str, ...] = Field(min_length=1)
    mandate_id: str = Field(min_length=1)
    mandate_revision: str = Field(min_length=1)
    ceilings: AggregateCeilings
    retention: RetentionDecision
    processing_plan: ProcessingPlan | None = None

    @field_validator("capture_specification_json")
    @classmethod
    def _capture_spec_is_canonical(cls, value: str) -> str:
        return _validate_canonical_json_object(value)

    @model_validator(mode="after")
    def _case_and_source_bindings_match(self) -> AcquisitionProposal:
        if self.need.case_id != self.case_id or self.retention.case_id != self.case_id:
            raise ValueError("proposal references must resolve within its case")
        if not set(self.expected_outcomes).issubset(set(self.need.answer_classes)):
            raise ValueError("expected outcomes must be declared by the discriminating need")
        if len(set(self.expected_outcomes)) != len(self.expected_outcomes):
            raise ValueError("expected outcomes must be unique")
        if self.processing_plan is not None:
            if self.processing_plan.input_transformation != "identity-bytes":
                raise ValueError("this coordinator only supports the identity-bytes input transformation")
            if self.processing_plan.case_id != self.case_id:
                raise ValueError("processing plan belongs to a different case")
            if self.processing_plan.authorized_source_id != self.source_id:
                raise ValueError("processing plan source does not match the authorized capture source")
            if self.processing_plan.destination != self.retention.destination:
                raise ValueError("processing destination does not match the retention decision")
            if self.processing_plan.retention_policy_id != self.retention.policy_id:
                raise ValueError("processing retention policy does not match the proposal")
            if self.processing_plan.retention_policy_version != self.retention.policy_version:
                raise ValueError("processing retention policy version does not match the proposal")
        return self


class AcquisitionAuthorization(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    authorization_id: str = Field(min_length=1)
    proposal_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    need_state_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    mandate_id: str = Field(min_length=1)
    mandate_revision: str = Field(min_length=1)
    authorizer_identity: str = Field(min_length=1)
    authentication_method: str = Field(min_length=1)
    retention_policy_id: str = Field(min_length=1)
    retention_policy_version: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def _authorization_window_is_valid(self) -> AcquisitionAuthorization:
        if self.issued_at.utcoffset() is None or self.expires_at.utcoffset() is None:
            raise ValueError("authorization timestamps must include timezones")
        if self.expires_at <= self.issued_at:
            raise ValueError("authorization expiry must follow its issue time")
        return self


class AcquisitionWorkflow(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    unknown_lock_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    proposal_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    authorization_id: str = Field(min_length=1)
    actor_identity: str = Field(min_length=1)
    reservation_id: str = Field(min_length=1)
    reserved_usage: ResourceUsage
    actual_usage: ResourceUsage
    current_phase: AcquisitionPhase | None = None
    unknown: bool = False


class ProcessorRequest(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=16_384)
    prompt_template_version: str = Field(min_length=1)
    parameters_json: str = Field(min_length=2, max_length=MAX_STRUCTURED_INPUT_BYTES)
    observation_id: str = Field(min_length=1)
    observation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_id: str = Field(min_length=1)
    input_transformation: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    usage_ceiling: ResourceUsage
    retention_policy_id: str = Field(min_length=1)
    retention_policy_version: str = Field(min_length=1)

    @field_validator("parameters_json")
    @classmethod
    def _parameters_are_canonical(cls, value: str) -> str:
        return _validate_canonical_json_object(value)


class SourceCaptureRequest(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    proposal_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    need_state_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_id: str = Field(min_length=1)
    source_capability_version: str = Field(min_length=1)
    capture_specification_json: str = Field(min_length=2)
    question: str = Field(min_length=1, max_length=16_384)
    retention_policy_id: str = Field(min_length=1)
    retention_policy_version: str = Field(min_length=1)
    usage_ceiling: ResourceUsage

    @field_validator("capture_specification_json")
    @classmethod
    def _capture_spec_is_canonical(cls, value: str) -> str:
        return _validate_canonical_json_object(value)


class AcquiredObservation(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    source_attempt_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_capability_version: str = Field(min_length=1)
    artifact_reference: str = Field(min_length=1)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_length: int = Field(strict=True, ge=0)
    captured_at: datetime
    actor: str = Field(min_length=1)
    retention_policy_id: str = Field(min_length=1)
    retention_policy_version: str = Field(min_length=1)

    @field_validator("captured_at")
    @classmethod
    def _capture_time_must_be_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("capture timestamp must include a timezone")
        return value


class AdapterAttempt(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    phase: AcquisitionPhase
    state: AttemptState
    request_reference: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    reservation_id: str = Field(min_length=1)
    reserved_usage: ResourceUsage
    actual_usage: ResourceUsage
    retention_policy_id: str = Field(min_length=1)
    retention_policy_version: str = Field(min_length=1)
    provider_request_id: str | None = None
    outcome_reason: str | None = None


class AnnotationCandidate(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    annotation_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    observation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    request_reference: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_reference: str = Field(min_length=1)
    output_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    usage: ResourceUsage
    is_empty: bool
    retention_policy_id: str = Field(min_length=1)
    retention_policy_version: str = Field(min_length=1)


class EvidenceEvaluation(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    evaluation_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    observation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    annotation_id: str | None = None
    annotation_digest: str | None = None
    evaluator_identity: str = Field(min_length=1)
    evaluator_type: Literal["human", "named_inference_mechanism"]
    criterion_id: str = Field(min_length=1)
    criterion_version: str = Field(min_length=1)
    outcome: EvaluationOutcome
    rationale: str = Field(min_length=1)
    evaluated_at: datetime

    @field_validator("evaluated_at")
    @classmethod
    def _evaluation_time_must_be_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("evaluation timestamp must include a timezone")
        return value

    @model_validator(mode="after")
    def _annotation_digest_matches_presence(self) -> EvidenceEvaluation:
        if (self.annotation_id is None) != (self.annotation_digest is None):
            raise ValueError("annotation ID and digest must be present together")
        return self


class UnknownResolution(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    resolution_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    disposition: UnknownDisposition
    actor_identity: str = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=16_384)
    resolved_at: datetime

    @field_validator("resolved_at")
    @classmethod
    def _resolution_time_must_be_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("resolution timestamp must include a timezone")
        return value


class AuthorizationRevocation(AcquisitionRecord):
    case_id: str = Field(min_length=1)
    authorization_id: str = Field(min_length=1)
    revocation_id: str = Field(min_length=1)
    actor_identity: str = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=16_384)
    revoked_at: datetime

    @field_validator("revoked_at")
    @classmethod
    def _revocation_time_must_be_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("revocation timestamp must include a timezone")
        return value


class AdapterResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    payload: Any
    usage: ResourceUsage
    provider_request_id: str | None = None


class AcquisitionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow: AcquisitionWorkflow
    observation: AcquiredObservation
    annotation: AnnotationCandidate | None
    evaluation: EvidenceEvaluation | None = None


class EvidenceSource(Protocol):
    def capture(self, request: SourceCaptureRequest, attempt: AdapterAttempt) -> AdapterResponse: ...


class EvidenceProcessor(Protocol):
    def process(
        self, request: ProcessorRequest, observation_bytes: bytes, attempt: AdapterAttempt
    ) -> AdapterResponse: ...


class AuthorizationGate(Protocol):
    """The implementation must make each method's database transition atomic."""

    def create_workflow(
        self,
        proposal: AcquisitionProposal,
        authorization: AcquisitionAuthorization,
        credential_proof: object,
        *,
        now: datetime,
    ) -> AcquisitionWorkflow: ...

    def begin_phase(
        self,
        workflow: AcquisitionWorkflow,
        phase: AcquisitionPhase,
        request: AcquisitionRecord,
        retention: RetentionDecision,
        credential_proof: object,
        *,
        now: datetime,
    ) -> AdapterAttempt: ...

    def complete_phase(
        self,
        attempt: AdapterAttempt,
        actual_usage: ResourceUsage,
        result: AcquiredObservation | AnnotationCandidate,
        *,
        provider_request_id: str | None = None,
        now: datetime,
    ) -> AcquisitionWorkflow: ...

    def mark_unknown(
        self,
        attempt: AdapterAttempt,
        reason: str,
        *,
        provider_request_id: str | None = None,
        now: datetime,
    ) -> None: ...

    def abort_before_phase_intent(
        self, workflow_id: str, phase: AcquisitionPhase, reason: str, *, now: datetime
    ) -> None: ...

    def fail_attempt_before_dispatch(
        self, workflow_id: str, phase: AcquisitionPhase, request_digest: str, reason: str, *, now: datetime
    ) -> None: ...

    def reconcile_unknown(
        self, attempt_id: str, resolution: UnknownResolution, credential_proof: object, *, now: datetime
    ) -> AcquisitionWorkflow: ...

    def revoke_authorization(
        self, revocation: AuthorizationRevocation, credential_proof: object, *, now: datetime
    ) -> None: ...

    def recover_interrupted_attempts(self, recovery_proof: object, *, now: datetime) -> int: ...


class ArtifactRepository(Protocol):
    def put_original(
        self,
        case_id: str,
        workflow_id: str,
        source_id: str,
        source_capability_version: str,
        source_attempt_id: str,
        actor_identity: str,
        content: bytes,
        retention: RetentionDecision,
    ) -> AcquiredObservation: ...

    def put_annotation(
        self,
        case_id: str,
        attempt_id: str,
        observation: AcquiredObservation,
        request: ProcessorRequest,
        response: bytes,
        retention: RetentionDecision,
    ) -> AnnotationCandidate: ...

    def read_verified(self, observation: AcquiredObservation) -> bytes: ...


class EvaluationSink(Protocol):
    def record(self, evaluation: EvidenceEvaluation) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


def canonical_record_digest(record: AcquisitionRecord) -> str:
    """Hash a schema-stamped, typed serialization of one acquisition record."""
    payload = record.model_dump(mode="json")
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def processor_request_for(
    plan: ProcessingPlan,
    observation: AcquiredObservation,
) -> ProcessorRequest:
    """Materialize only the digest from the observation authorized by the workflow."""
    if observation.case_id != plan.case_id:
        raise ValueError("observation and processing plan belong to different cases")
    if observation.source_id != plan.authorized_source_id:
        raise ValueError("observation source is outside the processing plan")
    return ProcessorRequest(
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


def verify_processor_request(
    plan: ProcessingPlan,
    observation: AcquiredObservation,
    request: ProcessorRequest,
) -> None:
    """Reject any request field that changed after the human approved the plan."""
    expected = processor_request_for(plan, observation)
    if request != expected:
        raise ValueError("processor request does not match the authorized processing plan")


def _usage_is_within(actual: ResourceUsage, ceiling: ResourceUsage) -> bool:
    return all(
        getattr(actual, name) <= getattr(ceiling, name)
        for name in ("usd_micros", "bytes", "frames", "duration_ms")
    )


class AcquisitionOutcomeUnknown(RuntimeError):
    def __init__(self, attempt_id: str, phase: AcquisitionPhase):
        super().__init__(f"acquisition attempt {attempt_id} has an unknown {phase.value} outcome")
        self.attempt_id = attempt_id
        self.phase = phase


class AcquisitionRecoveryRequired(RuntimeError):
    """A durable gate transition failed and needs explicit recovery."""


class AcquisitionCoordinator:
    def __init__(
        self,
        *,
        gate: AuthorizationGate,
        artifacts: ArtifactRepository,
        source: EvidenceSource,
        clock: Clock,
        processor: EvidenceProcessor | None = None,
    ):
        self._gate = gate
        self._artifacts = artifacts
        self._source = source
        self._clock = clock
        self._processor = processor

    def acquire(
        self,
        proposal: AcquisitionProposal,
        authorization: AcquisitionAuthorization,
        credential_proof: object,
    ) -> AcquisitionResult:
        if proposal.processing_plan is not None and self._processor is None:
            raise ValueError("approved processing plan has no configured processor")
        workflow = self._gate.create_workflow(
            proposal, authorization, credential_proof, now=self._clock.now()
        )
        proposal_digest = canonical_record_digest(proposal)
        if (
            workflow.case_id != proposal.case_id
            or workflow.proposal_digest != proposal_digest
            or workflow.authorization_id != authorization.authorization_id
            or workflow.actor_identity != authorization.authorizer_identity
        ):
            raise AcquisitionRecoveryRequired(
                "authorization gate returned a mismatched workflow; durable state must be reconciled"
            )

        capture_request = SourceCaptureRequest(
            case_id=proposal.case_id,
            proposal_digest=proposal_digest,
            need_state_digest=proposal.need.need_state_digest,
            source_id=proposal.source_id,
            source_capability_version=proposal.source_capability_version,
            capture_specification_json=proposal.capture_specification_json,
            question=proposal.need.question,
            retention_policy_id=proposal.retention.policy_id,
            retention_policy_version=proposal.retention.policy_version,
            usage_ceiling=proposal.source_usage_ceiling,
        )
        capture_attempt = self._begin_phase(
            workflow, AcquisitionPhase.SOURCE_CAPTURE, capture_request,
            retention=proposal.retention, credential_proof=credential_proof
        )
        try:
            response = None
            capture_started = time.monotonic()
            response = self._source.capture(capture_request, capture_attempt)
            source_bytes = self._collect_payload(
                response, proposal.source_usage_ceiling, started_at=capture_started
            )
            observation = self._artifacts.put_original(
                proposal.case_id,
                workflow.workflow_id,
                proposal.source_id,
                proposal.source_capability_version,
                capture_attempt.attempt_id,
                workflow.actor_identity,
                source_bytes,
                proposal.retention,
            )
            self._validate_observation(observation, workflow, proposal, capture_attempt, source_bytes)
            workflow = self._gate.complete_phase(
                capture_attempt, response.usage, observation,
                provider_request_id=getattr(response, "provider_request_id", None), now=self._clock.now()
            )
        except Exception as exc:
            self._mark_unknown(
                capture_attempt, type(exc).__name__,
                provider_request_id=getattr(response, "provider_request_id", None),
            )
            raise AcquisitionOutcomeUnknown(capture_attempt.attempt_id, AcquisitionPhase.SOURCE_CAPTURE) from exc

        annotation: AnnotationCandidate | None = None
        if proposal.processing_plan is not None:
            plan = proposal.processing_plan
            try:
                request = processor_request_for(plan, observation)
                verify_processor_request(plan, observation, request)
                source_bytes = self._artifacts.read_verified(observation)
                if hashlib.sha256(source_bytes).hexdigest() != observation.digest:
                    raise ValueError("artifact repository returned bytes with a mismatched digest")
            except Exception:
                self._abort_before_intent(
                    workflow, AcquisitionPhase.PROCESSOR_DERIVATION,
                    "processor_input_verification_failed"
                )
                raise
            processor_attempt = self._begin_phase(
                workflow, AcquisitionPhase.PROCESSOR_DERIVATION, request,
                retention=proposal.retention, credential_proof=credential_proof
            )
            try:
                response = None
                processor_started = time.monotonic()
                response = self._processor.process(request, source_bytes, processor_attempt)
                annotation_bytes = self._collect_payload(
                    response, plan.usage_ceiling, started_at=processor_started
                )
                annotation = self._artifacts.put_annotation(
                    proposal.case_id,
                    processor_attempt.attempt_id,
                    observation,
                    request,
                    annotation_bytes,
                    proposal.retention,
                )
                self._validate_annotation(annotation, processor_attempt, observation, request, annotation_bytes)
                workflow = self._gate.complete_phase(
                    processor_attempt, response.usage, annotation,
                    provider_request_id=getattr(response, "provider_request_id", None), now=self._clock.now()
                )
            except Exception as exc:
                self._mark_unknown(
                    processor_attempt, type(exc).__name__,
                    provider_request_id=getattr(response, "provider_request_id", None),
                )
                raise AcquisitionOutcomeUnknown(
                    processor_attempt.attempt_id, AcquisitionPhase.PROCESSOR_DERIVATION
                ) from exc

        return AcquisitionResult(workflow=workflow, observation=observation, annotation=annotation)

    def _begin_phase(
        self,
        workflow: AcquisitionWorkflow,
        phase: AcquisitionPhase,
        request: AcquisitionRecord,
        *,
        retention: RetentionDecision,
        credential_proof: object,
    ) -> AdapterAttempt:
        request_digest = canonical_record_digest(request)
        request_reference = f"sha256:{request_digest}"
        try:
            attempt = self._gate.begin_phase(
                workflow, phase, request, retention, credential_proof, now=self._clock.now()
            )
        except Exception as exc:
            self._abort_before_intent(workflow, phase, type(exc).__name__)
            raise
        try:
            matched = (
                isinstance(attempt, AdapterAttempt)
                and attempt.case_id == workflow.case_id
                and attempt.workflow_id == workflow.workflow_id
                and attempt.phase == phase
                and attempt.state == AttemptState.DISPATCH_INTENT
                and attempt.request_digest == request_digest
                and attempt.request_reference == request_reference
            )
        except Exception:
            matched = False
        if not matched:
            try:
                self._gate.fail_attempt_before_dispatch(
                    workflow.workflow_id, phase, request_digest,
                    "gate_returned_mismatched_attempt", now=self._clock.now()
                )
            except Exception as exc:
                raise AcquisitionRecoveryRequired(
                    "dispatch intent may be committed but could not be safely closed"
                ) from exc
            raise ValueError("dispatch gate did not return a matching committed dispatch attempt")
        return attempt

    def _abort_before_intent(
        self, workflow: AcquisitionWorkflow, phase: AcquisitionPhase, reason: str
    ) -> None:
        try:
            self._gate.abort_before_phase_intent(
                workflow.workflow_id, phase, reason, now=self._clock.now()
            )
        except Exception as exc:
            raise AcquisitionRecoveryRequired(
                f"{phase.value} may have durable state requiring recovery"
            ) from exc

    def _mark_unknown(
        self, attempt: AdapterAttempt, reason: str, *, provider_request_id: str | None = None
    ) -> None:
        try:
            self._gate.mark_unknown(
                attempt, reason, provider_request_id=provider_request_id, now=self._clock.now()
            )
        except Exception as exc:
            raise AcquisitionRecoveryRequired(
                f"{attempt.phase.value} dispatch may have occurred and UNKNOWN could not be persisted"
            ) from exc

    @staticmethod
    def _collect_payload(
        response: AdapterResponse, ceiling: ResourceUsage, *, started_at: float
    ) -> bytes:
        if isinstance(response.payload, (bytes, bytearray, memoryview)) or not callable(
            getattr(response.payload, "read", None)
        ):
            raise ValueError("adapter payload must be a readable binary stream")
        content = bytearray()
        total = 0
        reads = 0
        max_reads = max(1, min(4096, ceiling.bytes + 1))
        try:
            while True:
                if (time.monotonic() - started_at) * 1000 > ceiling.duration_ms:
                    raise ValueError("adapter stream exceeded its authorized duration ceiling")
                if reads >= max_reads:
                    raise ValueError("adapter stream exceeded its bounded read count")
                requested = min(64 * 1024, ceiling.bytes - total + 1)
                chunk = response.payload.read(requested)
                reads += 1
                if not isinstance(chunk, bytes):
                    raise ValueError("adapter payload stream must return bytes")
                if not chunk:
                    break
                if len(chunk) > requested:
                    raise ValueError("adapter stream returned more bytes than the bounded read requested")
                total += len(chunk)
                if total > ceiling.bytes:
                    raise ValueError("adapter payload exceeded its authorized byte ceiling")
                content.extend(chunk)
            if response.usage.bytes != total:
                raise ValueError("adapter-reported byte usage does not match the streamed payload")
            if not _usage_is_within(response.usage, ceiling):
                raise ValueError("adapter response exceeded its authorized usage ceiling")
            if (time.monotonic() - started_at) * 1000 > ceiling.duration_ms:
                raise ValueError("adapter response exceeded its authorized duration ceiling")
            return bytes(content)
        finally:
            close = getattr(response.payload, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _validate_observation(
        observation: AcquiredObservation,
        workflow: AcquisitionWorkflow,
        proposal: AcquisitionProposal,
        attempt: AdapterAttempt,
        content: bytes,
    ) -> None:
        if (
            observation.case_id != proposal.case_id
            or observation.workflow_id != workflow.workflow_id
            or observation.source_attempt_id != attempt.attempt_id
            or attempt.phase != AcquisitionPhase.SOURCE_CAPTURE
            or attempt.workflow_id != workflow.workflow_id
            or observation.source_id != proposal.source_id
            or observation.source_capability_version != proposal.source_capability_version
            or observation.actor != workflow.actor_identity
            or observation.retention_policy_id != proposal.retention.policy_id
            or observation.retention_policy_version != proposal.retention.policy_version
            or observation.digest != hashlib.sha256(content).hexdigest()
            or observation.artifact_reference != f"sha256:{observation.digest}"
            or observation.byte_length != len(content)
        ):
            raise ValueError("artifact repository returned an observation that does not match captured bytes")

    @staticmethod
    def _validate_annotation(
        annotation: AnnotationCandidate,
        attempt: AdapterAttempt,
        observation: AcquiredObservation,
        request: ProcessorRequest,
        content: bytes,
    ) -> None:
        if (
            annotation.case_id != observation.case_id
            or annotation.observation_id != observation.observation_id
            or annotation.observation_digest != observation.digest
            or annotation.attempt_id != attempt.attempt_id
            or annotation.provider_id != request.provider_id
            or annotation.model_id != request.model_id
            or annotation.model_version != request.model_version
            or annotation.request_digest != canonical_record_digest(request)
            or annotation.request_reference != f"sha256:{annotation.request_digest}"
            or annotation.output_reference != f"sha256:{annotation.output_digest}"
            or annotation.output_digest != hashlib.sha256(content).hexdigest()
            or annotation.usage.bytes != len(content)
            or not _usage_is_within(annotation.usage, request.usage_ceiling)
            or annotation.retention_policy_id != observation.retention_policy_id
            or annotation.retention_policy_version != observation.retention_policy_version
            or annotation.retention_policy_id != attempt.retention_policy_id
            or annotation.retention_policy_version != attempt.retention_policy_version
            or annotation.is_empty != (len(content) == 0)
        ):
            raise ValueError("artifact repository returned an annotation with mismatched provenance")
