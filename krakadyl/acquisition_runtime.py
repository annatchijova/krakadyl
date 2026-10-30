"""Deployment components that turn the acquisition contract into a usable path.

`core/acquisition.py` and `core/acquisition_store.py` define the
contract and the durable gate but deliberately ship no identity, scope,
budget, retention, artifact, or source implementation. This module
supplies the smallest honest set of those for a local, single-host
KRAKADYL deployment — and fails closed when any of them is missing:

- Identity: operator bearer tokens, configured only as SHA-256 hashes
  (`KRAKADYL_OPERATOR_TOKENS`). A request's identity is whatever token it
  proves, never a name it asserts. This is real authentication of a
  shared secret, not an identity provider: no expiry, rotation, or MFA.
- Source: operator-mediated capture. KRAKADYL cannot point a camera at
  anything; the authorized investigator takes the photograph and submits
  the bytes in the same authenticated request that dispatches the
  capture. The bytes are held in memory until the gate admits the
  workflow, and are persisted only through the write-once repository.
- Artifacts: write-once, content-addressed files, re-hashed on every read.
- Processor: Meta SAM 3.1 only when an API key AND an explicit opt-in are
  configured; otherwise proposals carry no processing plan at all.
- Recovery: no automated quiescence attestation exists here, so
  interrupted dispatches stay UNKNOWN until a human reconciles them.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional

from krakadyl.adapters.sam import (
    API_DESTINATION as SAM_DESTINATION,
    IMAGE_PRICE_USD_MICROS,
    MAX_INPUT_BYTES,
    MAX_PROMPT_CHARS,
    MODEL_ID as SAM_MODEL_ID,
    MetaSamProcessor,
)
from krakadyl.core.acquisition import (
    AcquiredObservation,
    AcquisitionAuthorization,
    AcquisitionCoordinator,
    AcquisitionPhase,
    AcquisitionProposal,
    AcquisitionResult,
    AdapterAttempt,
    AdapterResponse,
    AggregateCeilings,
    AnnotationCandidate,
    AttemptState,
    ProcessingPlan,
    ProcessorRequest,
    ResourceUsage,
    RetentionDecision,
    SourceCaptureRequest,
    canonical_json_object,
    canonical_record_digest,
)
from krakadyl.core.acquisition_routes import (
    CAPTURE_OPERATION,
    DERIVE_OPERATION,
    LOCAL_DESTINATION,
    AcquisitionRoute,
    RouteRefusal,
    SourceCapability,
    acquisition_route,
    need_snapshot_for,
)
from krakadyl.core.acquisition_store import SQLiteAcquisitionGate
from krakadyl.core.executor import check_mandate
from krakadyl.core.models import AuthorityState, EvidenceRequirement, Hypothesis, Mandate
from krakadyl.store import KrakadylStore

OPERATOR_AUTH_METHOD = "operator-bearer-token-sha256"
AUTHORIZATION_TTL = timedelta(minutes=15)
RETENTION_POLICY_ID = "krakadyl-local-case-retention"
RETENTION_POLICY_VERSION = "1"
RETENTION_SECONDS = 90 * 24 * 3600
SAM_PROMPT_TEMPLATE_VERSION = "concept-prompt-v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")

OPERATOR_INTAKE = SourceCapability(
    source_id="operator-intake",
    capability_version="operator-intake-v1",
    source_class="operator photograph",
    description=(
        "The authorized investigator photographs the item themself and submits the "
        "original PNG/JPEG bytes in the same authenticated request that dispatches the capture."
    ),
)


class AcquisitionUnavailable(RuntimeError):
    """A required deployment component is not configured; nothing was attempted."""


class CredentialRejected(ValueError):
    pass


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OperatorCredentials:
    token_hashes: dict[str, str]  # identity -> sha256(token)

    @classmethod
    def parse(cls, value: str) -> "OperatorCredentials":
        """`identity=sha256hex;identity2=sha256hex` — hashes only, never tokens."""
        hashes: dict[str, str] = {}
        for entry in filter(None, (part.strip() for part in value.split(";"))):
            identity, _, digest = entry.partition("=")
            identity, digest = identity.strip(), digest.strip().lower()
            if not _SAFE_ID.match(identity) or not _SHA256.match(digest):
                raise ValueError("operator credential entries must be 'identity=<sha256 hex>'")
            if identity in hashes or digest in hashes.values():
                raise ValueError("operator identities and token hashes must be unique")
            hashes[identity] = digest
        return cls(token_hashes=hashes)

    def identify(self, token: object) -> str:
        if not isinstance(token, str) or not token or len(token) > 512:
            raise CredentialRejected("no valid operator credential presented")
        presented = hash_token(token)
        match = None
        for identity, expected in self.token_hashes.items():
            # Compare against every entry so timing does not reveal position.
            if hmac.compare_digest(presented, expected):
                match = identity
        if match is None:
            raise CredentialRejected("operator credential is not recognized")
        return match


class OperatorAuthorizationVerifier:
    def __init__(self, credentials: OperatorCredentials):
        self._credentials = credentials

    def verify(self, proposal, authorization, proof, now) -> str:
        if authorization.authentication_method != OPERATOR_AUTH_METHOD:
            raise CredentialRejected("authorization was not issued by operator authentication")
        return self._credentials.identify(proof)


class OperatorResolutionVerifier:
    def __init__(self, credentials: OperatorCredentials):
        self._credentials = credentials

    def verify(self, resolution, authorization, proof, now) -> str:
        return self._credentials.identify(proof)


class OperatorRevocationVerifier:
    def __init__(self, credentials: OperatorCredentials):
        self._credentials = credentials

    def verify(self, revocation, proof, now) -> str:
        return self._credentials.identify(proof)


class NoQuiescenceAttestation:
    """No process supervisor here can prove that no dispatch is in flight,
    so automated recovery never succeeds; a human reconciles instead."""

    def verify(self, proof, dispatch_generation, now) -> bool:
        return False


class MandateScopePolicy:
    """The capture mandate's principal is the only identity that may
    authorize or dispatch; each phase needs its own operation and
    destination in that mandate."""

    def authorize(self, identity, mandate: Mandate, proposal: AcquisitionProposal, phase, now) -> None:
        if identity != mandate.principal:
            raise ValueError(f"capture mandate is scoped to '{mandate.principal}', not '{identity}'")
        if phase == AcquisitionPhase.SOURCE_CAPTURE:
            operation, destination = CAPTURE_OPERATION, LOCAL_DESTINATION
        else:
            if proposal.processing_plan is None:
                raise ValueError("processor phase has no approved processing plan")
            operation, destination = DERIVE_OPERATION, proposal.processing_plan.destination
        check = check_mandate(
            mandate,
            resource=f"{proposal.case_id}/{proposal.source_id}",
            operation=operation,
            destination=destination,
            now=now,
        )
        if check.outside_scope or check.authority_state != AuthorityState.GRANTED:
            raise ValueError("; ".join(check.reasons))


@dataclass(frozen=True)
class ConfiguredBudgets:
    per_requirement: ResourceUsage
    per_case_mandate: ResourceUsage
    deployment: ResourceUsage

    def cap(self, scope_type: str, scope_id: str) -> ResourceUsage:
        caps = {
            "requirement": self.per_requirement,
            "case_mandate": self.per_case_mandate,
            "deployment": self.deployment,
        }
        if scope_type not in caps:
            raise ValueError(f"no budget is configured for scope '{scope_type}'")
        return caps[scope_type]

    def as_ceilings(self) -> AggregateCeilings:
        return AggregateCeilings(
            per_requirement=self.per_requirement,
            per_case_mandate=self.per_case_mandate,
            deployment_account=self.deployment,
        )


def _usage(usd_micros: int, bytes_count: int, frames: int, duration_ms: int) -> ResourceUsage:
    return ResourceUsage(usd_micros=usd_micros, bytes=bytes_count, frames=frames, duration_ms=duration_ms)


DEFAULT_BUDGETS = ConfiguredBudgets(
    # Four SAM image calls per requirement, twenty per case, forty per deployment.
    per_requirement=_usage(4 * IMAGE_PRICE_USD_MICROS, 4 * (MAX_INPUT_BYTES + 8 * 1024 * 1024), 0, 4 * 180_000),
    per_case_mandate=_usage(20 * IMAGE_PRICE_USD_MICROS, 20 * (MAX_INPUT_BYTES + 8 * 1024 * 1024), 0, 20 * 180_000),
    deployment=_usage(40 * IMAGE_PRICE_USD_MICROS, 40 * (MAX_INPUT_BYTES + 8 * 1024 * 1024), 0, 40 * 180_000),
)
SOURCE_CEILING = _usage(0, MAX_INPUT_BYTES, 0, 60_000)
SAM_CEILING = _usage(IMAGE_PRICE_USD_MICROS, 8 * 1024 * 1024, 0, 120_000)


class LocalRetentionPolicy:
    def __init__(self, *, allowed_destinations: frozenset[str]):
        self._allowed = allowed_destinations

    def decision_for(self, case_id: str, destination: str) -> RetentionDecision:
        if destination not in self._allowed:
            raise ValueError(f"no retention decision covers destination '{destination}'")
        categories = ("case-capture-image",) if destination == LOCAL_DESTINATION else (
            "case-capture-image", "derived-annotation", "third-party-processing-transfer"
        )
        return RetentionDecision(
            case_id=case_id,
            policy_id=RETENTION_POLICY_ID,
            policy_version=RETENTION_POLICY_VERSION,
            data_categories=categories,
            destination=destination,
            retention_seconds=RETENTION_SECONDS,
            disposition="retain-with-case-then-human-review",
            decided_by="deployment-configuration",
        )

    def current(self, proposal: AcquisitionProposal, now) -> RetentionDecision:
        return self.decision_for(proposal.case_id, proposal.retention.destination)


def _safe_component(value: str) -> str:
    if not _SAFE_ID.match(value) or value in {".", ".."}:
        raise ValueError("identifier is not safe to use as a path component")
    return value


class FilesystemArtifactRepository:
    """Write-once and content-addressed: `<root>/<case>/<kind>/<sha256>`.

    A second write of identical bytes is idempotent; there is no code
    path that writes different bytes under an existing digest, and every
    read re-hashes before returning anything."""

    def __init__(self, root: Path):
        self._root = root

    def _path(self, case_id: str, kind: str, digest: str) -> Path:
        if not _SHA256.match(digest):
            raise ValueError("artifact digest is malformed")
        return self._root / _safe_component(case_id) / kind / digest

    def _write_once(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != path.name:
                raise ValueError("existing content-addressed artifact failed digest verification")
            return
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.partial")
        with open(temporary, "xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)  # fails instead of replacing if another writer won
        except FileExistsError:
            pass
        finally:
            temporary.unlink(missing_ok=True)
        if hashlib.sha256(path.read_bytes()).hexdigest() != path.name:
            raise ValueError("artifact failed digest verification after write")

    def _read(self, case_id: str, kind: str, digest: str) -> bytes:
        content = self._path(case_id, kind, digest).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("stored artifact failed read-time digest verification")
        return content

    def put_original(
        self, case_id, workflow_id, source_id, source_capability_version, source_attempt_id,
        actor_identity, content, retention,
    ) -> AcquiredObservation:
        digest = hashlib.sha256(content).hexdigest()
        self._write_once(self._path(case_id, "originals", digest), content)
        return AcquiredObservation(
            case_id=case_id,
            observation_id=f"acquired-{source_attempt_id}",
            workflow_id=workflow_id,
            source_attempt_id=source_attempt_id,
            source_id=source_id,
            source_capability_version=source_capability_version,
            artifact_reference=f"sha256:{digest}",
            digest=digest,
            byte_length=len(content),
            captured_at=datetime.now().astimezone(),
            actor=actor_identity,
            retention_policy_id=retention.policy_id,
            retention_policy_version=retention.policy_version,
        )

    def put_annotation(
        self, case_id, attempt_id, observation, request: ProcessorRequest, response, retention, usage
    ) -> AnnotationCandidate:
        # The exact request record itself is kept by the gate
        # (acquisition_requests, bound to its retention decision).
        request_digest = canonical_record_digest(request)
        output_digest = hashlib.sha256(response).hexdigest()
        self._write_once(self._path(case_id, "annotations", output_digest), response)
        return AnnotationCandidate(
            case_id=case_id,
            annotation_id=f"annotation-{attempt_id}",
            observation_id=observation.observation_id,
            observation_digest=observation.digest,
            attempt_id=attempt_id,
            provider_id=request.provider_id,
            model_id=request.model_id,
            model_version=request.model_version,
            request_reference=f"sha256:{request_digest}",
            request_digest=request_digest,
            output_reference=f"sha256:{output_digest}",
            output_digest=output_digest,
            usage=usage,
            is_empty=not response,
            retention_policy_id=retention.policy_id,
            retention_policy_version=retention.policy_version,
        )

    def read_verified(self, observation: AcquiredObservation) -> bytes:
        return self._read(observation.case_id, "originals", observation.digest)

    def read_annotation(self, annotation: AnnotationCandidate) -> bytes:
        return self._read(annotation.case_id, "annotations", annotation.output_digest)


def image_mime(content: bytes) -> Optional[str]:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


class OperatorIntakeSource:
    """Returns exactly the bytes the authenticated operator submitted —
    only after the gate committed this attempt's dispatch intent."""

    def __init__(self, content: bytes):
        if not isinstance(content, bytes) or not content:
            raise ValueError("an operator capture must contain image bytes")
        if len(content) > MAX_INPUT_BYTES:
            raise ValueError("operator capture exceeds the 10 MiB image limit")
        if image_mime(content) is None:
            raise ValueError("operator capture must be a PNG or JPEG image")
        self._content = content

    def capture(self, request: SourceCaptureRequest, attempt: AdapterAttempt) -> AdapterResponse:
        if (
            request.source_id != OPERATOR_INTAKE.source_id
            or attempt.phase != AcquisitionPhase.SOURCE_CAPTURE
            or attempt.state != AttemptState.DISPATCH_INTENT
            or attempt.request_digest != canonical_record_digest(request)
        ):
            raise ValueError("operator intake attempt does not match its committed capture request")
        return AdapterResponse(
            payload=BytesIO(self._content),
            usage=_usage(0, len(self._content), 0, 0),
        )


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now().astimezone()


@dataclass
class AcquisitionRuntime:
    store: KrakadylStore
    credentials: OperatorCredentials
    artifacts: FilesystemArtifactRepository
    sam_processor: Optional[MetaSamProcessor] = None
    budgets: ConfiguredBudgets = DEFAULT_BUDGETS
    sources: list[SourceCapability] = field(default_factory=lambda: [OPERATOR_INTAKE])
    clock: object = field(default_factory=_SystemClock)

    def __post_init__(self) -> None:
        if not self.credentials.token_hashes:
            raise AcquisitionUnavailable("no operator credentials are configured")
        destinations = {LOCAL_DESTINATION}
        if self.sam_processor is not None:
            destinations.add(SAM_DESTINATION)
        self.retention = LocalRetentionPolicy(allowed_destinations=frozenset(destinations))
        self.gate = SQLiteAcquisitionGate(
            store=self.store,
            authorization_verifier=OperatorAuthorizationVerifier(self.credentials),
            scope_policy=MandateScopePolicy(),
            budget_policy=self.budgets,
            retention_policy=self.retention,
            unknown_resolution_verifier=OperatorResolutionVerifier(self.credentials),
            revocation_verifier=OperatorRevocationVerifier(self.credentials),
            recovery_quiescence_verifier=NoQuiescenceAttestation(),
            deployment_scope_id="krakadyl-local-deployment",
            recovery_stale_after_seconds=300,
        )

    @property
    def sam_enabled(self) -> bool:
        return self.sam_processor is not None

    def route(self, *, case_id, requirement, hypotheses, capture_mandate, now) -> AcquisitionRoute | RouteRefusal:
        return acquisition_route(
            case_id=case_id,
            requirement=requirement,
            hypotheses=hypotheses,
            capture_mandate=capture_mandate,
            sources=self.sources,
            now=now,
        )

    def build_proposal(
        self,
        *,
        case_id: str,
        requirement: EvidenceRequirement,
        hypotheses: list[Hypothesis],
        capture_mandate: Optional[Mandate],
        capture_instructions: str,
        sam_prompt: Optional[str],
        now: datetime,
    ) -> AcquisitionProposal:
        route = self.route(
            case_id=case_id, requirement=requirement, hypotheses=hypotheses,
            capture_mandate=capture_mandate, now=now,
        )
        if isinstance(route, RouteRefusal):
            raise ValueError(f"no authorized acquisition route: {route.reason}")
        if not capture_instructions.strip() or len(capture_instructions) > 2000:
            raise ValueError("capture instructions must be between 1 and 2000 characters")
        plan = None
        destination = LOCAL_DESTINATION
        if sam_prompt is not None:
            if not self.sam_enabled:
                raise AcquisitionUnavailable("SAM processing is not enabled in this deployment")
            prompt = sam_prompt.strip()
            if not prompt or len(prompt) > MAX_PROMPT_CHARS:
                raise ValueError(f"SAM concept prompt must be 1–{MAX_PROMPT_CHARS} characters")
            destination = SAM_DESTINATION
            plan = ProcessingPlan(
                case_id=case_id,
                capability_id="meta-sam-image-segmentation",
                capability_version="1",
                provider_id="meta",
                model_id=SAM_MODEL_ID,
                model_version=SAM_MODEL_ID,
                prompt=prompt,
                prompt_template_version=SAM_PROMPT_TEMPLATE_VERSION,
                parameters_json="{}",
                authorized_source_id=route.source_id,
                input_transformation="identity-bytes",
                destination=SAM_DESTINATION,
                usage_ceiling=SAM_CEILING,
                retention_policy_id=RETENTION_POLICY_ID,
                retention_policy_version=RETENTION_POLICY_VERSION,
            )
        return AcquisitionProposal(
            case_id=case_id,
            need=need_snapshot_for(case_id=case_id, requirement=requirement, hypotheses=hypotheses),
            source_id=route.source_id,
            source_capability_version=route.source_capability_version,
            capture_specification_json=canonical_json_object({
                "kind": "operator_photograph",
                "instructions": capture_instructions.strip(),
                "accepted_media": ["image/jpeg", "image/png"],
            }),
            source_usage_ceiling=SOURCE_CEILING,
            expected_outcomes=route.answer_classes,
            mandate_id=route.mandate_id,
            mandate_revision=route.mandate_revision,
            ceilings=self.budgets.as_ceilings(),
            retention=self.retention.decision_for(case_id, destination),
            processing_plan=plan,
        )

    def authorize(self, proposal: AcquisitionProposal, token: str, now: datetime) -> AcquisitionAuthorization:
        """The human approval: bound to the exact proposal digest, issued
        to the identity the token proves, single-use, short-lived."""
        identity = self.credentials.identify(token)
        return AcquisitionAuthorization(
            case_id=proposal.case_id,
            authorization_id=f"authorization-{secrets.token_hex(12)}",
            proposal_digest=canonical_record_digest(proposal),
            need_state_digest=proposal.need.need_state_digest,
            mandate_id=proposal.mandate_id,
            mandate_revision=proposal.mandate_revision,
            authorizer_identity=identity,
            authentication_method=OPERATOR_AUTH_METHOD,
            retention_policy_id=proposal.retention.policy_id,
            retention_policy_version=proposal.retention.policy_version,
            issued_at=now,
            expires_at=now + AUTHORIZATION_TTL,
        )

    def acquire(
        self,
        proposal: AcquisitionProposal,
        authorization: AcquisitionAuthorization,
        token: str,
        content: bytes,
    ) -> AcquisitionResult:
        coordinator = AcquisitionCoordinator(
            gate=self.gate,
            artifacts=self.artifacts,
            source=OperatorIntakeSource(content),
            clock=self.clock,
            processor=self.sam_processor,
        )
        return coordinator.acquire(proposal, authorization, token)


def runtime_from_environment(store: KrakadylStore, data_dir: Path) -> Optional[AcquisitionRuntime]:
    """None (acquisition disabled, every endpoint says so) unless operator
    credentials are configured. SAM additionally needs both a key and
    `KRAKADYL_ENABLE_SAM=1` — a key alone never enables billed calls."""
    credentials = os.environ.get("KRAKADYL_OPERATOR_TOKENS", "").strip()
    if not credentials:
        return None
    processor = None
    if os.environ.get("KRAKADYL_ENABLE_SAM") == "1":
        api_key = os.environ.get("META_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("KRAKADYL_ENABLE_SAM=1 requires META_API_KEY")
        processor = MetaSamProcessor(api_key=api_key)
    return AcquisitionRuntime(
        store=store,
        credentials=OperatorCredentials.parse(credentials),
        artifacts=FilesystemArtifactRepository(data_dir / "acquired"),
        sam_processor=processor,
    )
