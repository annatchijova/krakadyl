from io import BytesIO
import json

from krakadyl.adapters.sam import API_DESTINATION, MetaSamProcessor
from krakadyl.core.acquisition import (
    AcquisitionCoordinator,
    AdapterAttempt,
    AdapterResponse,
    AggregateCeilings,
    AnnotationCandidate,
    AttemptState,
    ResourceUsage,
    canonical_record_digest,
)
from krakadyl.core.models import Mandate
from krakadyl.store import KrakadylStore
from test_acquisition_contract import _FakeClock, _MemoryArtifacts, _usage
from test_sqlite_acquisition_gate import NOW, _gate, _records


PNG = b"\x89PNG\r\n\x1a\nsynthetic-sqlite-fixture"
SAM_TEXT = "<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10|><|mask;x=0;y=0;data=1,2|>"


class _SyntheticPngSource:
    def capture(self, request, attempt):
        return AdapterResponse(
            payload=BytesIO(PNG),
            usage=ResourceUsage(usd_micros=0, bytes=len(PNG), frames=0, duration_ms=1),
        )


def test_sqlite_gate_persists_sam_annotation_usage_and_provider_request_id(tmp_path):
    proposal, authorization, requirement, hypothesis, mandate = _records()
    plan = proposal.processing_plan.model_copy(update={
        "provider_id": "meta",
        "model_id": "sam-3.1",
        "model_version": "sam-3.1",
        "prompt": "red square",
        "parameters_json": "{}",
        "destination": API_DESTINATION,
        "usage_ceiling": _usage(usd_micros=2500, bytes_count=4096, frames=0, duration_ms=60_000),
    })
    ceilings = AggregateCeilings(
        per_requirement=_usage(usd_micros=2500, bytes_count=8192, duration_ms=62_000),
        per_case_mandate=_usage(usd_micros=5000, bytes_count=16_384, duration_ms=124_000),
        deployment_account=_usage(usd_micros=10_000, bytes_count=32_768, duration_ms=248_000),
    )
    retention = proposal.retention.model_copy(update={"destination": API_DESTINATION})
    proposal = type(proposal).model_validate({
        **proposal.model_dump(),
        "processing_plan": plan,
        "ceilings": ceilings,
        "retention": retention,
    })
    authorization = authorization.model_copy(update={
        "proposal_digest": canonical_record_digest(proposal),
    })
    mandate = Mandate.model_validate({
        **mandate.model_dump(), "destinations": [API_DESTINATION],
    })
    store = KrakadylStore(tmp_path / "sam-acquisition.db")
    store.put(proposal.case_id, "requirement", requirement, NOW.isoformat())
    store.put(proposal.case_id, "hypothesis", hypothesis, NOW.isoformat())
    store.put(proposal.case_id, "mandate", mandate, NOW.isoformat())

    processor = MetaSamProcessor(
        api_key="synthetic-test-key",
        transport=lambda *args: (
            200,
            {"x-request-id": "meta-sam-sqlite-canary"},
            json.dumps({
                "id": "meta-response-synthetic",
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": SAM_TEXT}]}],
            }).encode(),
        ),
    )
    artifacts = _MemoryArtifacts()
    coordinator = AcquisitionCoordinator(
        gate=_gate(store),
        artifacts=artifacts,
        source=_SyntheticPngSource(),
        processor=processor,
        clock=_FakeClock(),
    )

    result = coordinator.acquire(proposal, authorization, "test-proof-do-not-persist")

    assert result.annotation is not None
    assert result.annotation.is_empty is False
    assert result.annotation.usage.usd_micros == 2500
    assert result.evaluation is None
    persisted_attempt, persisted_annotation = store.read_locked(lambda connection: connection.execute(
        "SELECT a.attempt_json, a.result_json "
        "FROM acquisition_attempts a WHERE a.phase='processor_derivation'"
    ).fetchone())
    attempt = AdapterAttempt.model_validate_json(persisted_attempt)
    annotation = AnnotationCandidate.model_validate_json(persisted_annotation)
    assert attempt.state == AttemptState.COMPLETED
    assert attempt.provider_request_id == "meta-sam-sqlite-canary"
    assert attempt.actual_usage.usd_micros == 2500
    assert annotation.usage == attempt.actual_usage
    assert annotation.observation_digest == result.observation.digest
    assert store.read_locked(lambda connection: connection.execute(
        "SELECT state FROM acquisition_workflows WHERE workflow_id=?",
        (result.workflow.workflow_id,),
    ).fetchone()[0]) == "completed"
    committed = store.read_locked(lambda connection: connection.execute(
        "SELECT committed_json FROM acquisition_reservations "
        "WHERE workflow_id=? AND scope_type='requirement'",
        (result.workflow.workflow_id,),
    ).fetchone()[0])
    assert ResourceUsage.model_validate_json(committed).usd_micros == 2500
    store.close()
