import base64
import hashlib
import json
import socket
from io import BytesIO
import time
import pytest

from krakadyl.adapters.sam import (
    MetaSamProcessor,
    SamAdapterError,
    _call_with_absolute_deadline,
    _read_bounded_body,
)
from krakadyl.core.acquisition import AdapterAttempt, AdapterResponse, AcquisitionPhase, AttemptState, ProcessorRequest, ResourceUsage, canonical_json_object, canonical_record_digest
from test_acquisition_contract import _MemoryGate, _proposal_and_authorization, _usage


PNG = b"\x89PNG\r\n\x1a\nfixture"


def _request(*, prompt="red square", ceiling_usd=2500, parameters=None):
    return ProcessorRequest(
        case_id="case-synthetic",
        plan_digest="a" * 64,
        provider_id="meta",
        model_id="sam-3.1",
        model_version="sam-3.1",
        prompt=prompt,
        prompt_template_version="1",
        parameters_json=canonical_json_object(parameters or {}),
        observation_id="observation-synthetic",
        observation_digest=hashlib.sha256(PNG).hexdigest(),
        source_id="fixture-source",
        input_transformation="identity-bytes",
        destination="https://api.meta.ai/v1",
        usage_ceiling=ResourceUsage(usd_micros=ceiling_usd, bytes=4096, frames=0, duration_ms=60_000),
        retention_policy_id="synthetic-retention",
        retention_policy_version="1",
    )


def _attempt(request):
    return AdapterAttempt(
        case_id=request.case_id,
        attempt_id="attempt-synthetic",
        workflow_id="workflow-synthetic",
        phase=AcquisitionPhase.PROCESSOR_DERIVATION,
        state=AttemptState.DISPATCH_INTENT,
        request_reference="sha256:" + canonical_record_digest(request),
        request_digest=canonical_record_digest(request),
        reservation_id="reservation-synthetic",
        reserved_usage=request.usage_ceiling,
        actual_usage=ResourceUsage(usd_micros=0, bytes=0, frames=0, duration_ms=0),
        retention_policy_id=request.retention_policy_id,
        retention_policy_version=request.retention_policy_version,
    )


def _response(text="<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10|><|mask;x=0;y=0;data=1,2|>", *, request_id="req-synthetic"):
    return {"id": request_id, "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


def test_sam_request_contains_only_authorized_image_and_prompt():
    seen = {}

    def transport(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=json.loads(body), timeout=timeout)
        return 200, {"x-request-id": "req-header"}, json.dumps(_response()).encode()

    processor = MetaSamProcessor(api_key="secret-test-key", transport=transport)
    request = _request()
    processor.validate_request(request, PNG)
    response = processor.process(request, PNG, _attempt(request))

    payload = response.payload.read()
    assert payload.startswith(b"<0f>")
    assert response.provider_request_id == "req-header"
    assert response.usage.usd_micros == 2500
    assert response.usage.bytes == len(payload)
    assert seen["url"] == "https://api.meta.ai/v1/responses"
    assert seen["headers"]["Authorization"] == "Bearer secret-test-key"
    image = seen["body"]["input"][0]["content"][1]["image_url"]
    assert image == "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")
    assert seen["body"]["input"][0]["content"][0]["text"] == "red square"
    assert seen["body"]["stream"] is False


def test_sam_empty_output_is_preserved_as_empty_candidate():
    processor = MetaSamProcessor(
        api_key="secret-test-key",
        transport=lambda *args: (200, {}, json.dumps(_response("")).encode()),
    )
    request = _request()
    response = processor.process(request, PNG, _attempt(request))

    assert response.payload.read() == b""
    assert response.usage.usd_micros == 2500


def test_sam_missing_output_text_is_not_collapsed_into_a_valid_empty_result():
    malformed = {"id": "req-synthetic", "status": "completed", "output": []}
    processor = MetaSamProcessor(
        api_key="secret-test-key",
        transport=lambda *args: (200, {}, json.dumps(malformed).encode()),
    )

    with pytest.raises(SamAdapterError, match="omitted output_text"):
        processor.process(_request(), PNG, _attempt(_request()))


def test_sam_slow_drip_cannot_extend_absolute_response_deadline():
    deadlines = []

    def slow_read(size):
        time.sleep(0.02)
        return b"partial"

    with pytest.raises(SamAdapterError, match="absolute duration limit") as captured:
        _read_bounded_body(
            slow_read,
            deadlines.append,
            deadline=time.monotonic() + 0.01,
            provider_request_id="req-slow-drip",
        )

    assert deadlines[0] > 0
    assert captured.value.provider_request_id == "req-slow-drip"


def test_sam_slow_response_headers_are_interrupted_at_absolute_deadline():
    local_client, local_server = socket.socketpair()
    try:
        with pytest.raises(SamAdapterError, match="absolute duration limit"):
            _call_with_absolute_deadline(
                lambda: local_client.recv(1),
                lambda: local_client.shutdown(socket.SHUT_RDWR),
                deadline=time.monotonic() + 0.02,
                provider_request_id=None,
            )
    finally:
        local_client.close()
        local_server.close()


@pytest.mark.parametrize(
    "changes, content, match",
    [
        ({"usage_ceiling": ResourceUsage(usd_micros=2499, bytes=4096, frames=0, duration_ms=60_000)}, PNG, "price ceiling"),
        ({"parameters_json": canonical_json_object({"arbitrary": True})}, PNG, "parameters"),
        ({}, b"not an image", "PNG or JPEG"),
        ({}, PNG + b"x", "digest"),
        ({"prompt": "x" * 257}, PNG, "256 characters"),
    ],
)
def test_sam_preflight_rejects_unbounded_or_mismatched_inputs(changes, content, match):
    request = _request().model_copy(update=changes)
    processor = MetaSamProcessor(api_key="secret-test-key", transport=lambda *args: pytest.fail("transport called"))

    with pytest.raises(ValueError, match=match):
        processor.validate_request(request, content)


def test_sam_dispatch_error_keeps_provider_request_id_without_exposing_response_body():
    def transport(*args):
        return 429, {"x-request-id": "req-rate-limit"}, b"sensitive provider body"

    processor = MetaSamProcessor(api_key="secret-test-key", transport=transport)
    request = _request()

    with pytest.raises(SamAdapterError) as captured:
        processor.process(request, PNG, _attempt(request))

    assert captured.value.provider_request_id == "req-rate-limit"
    assert "sensitive provider body" not in str(captured.value)


def test_sam_processor_completes_coordinator_as_untrusted_annotation_only():
    from krakadyl.core.acquisition import AcquisitionCoordinator, AggregateCeilings
    from test_acquisition_contract import _MemoryArtifacts, _SyntheticSource, _FakeClock

    proposal, authorization = _proposal_and_authorization()
    plan = proposal.processing_plan.model_copy(update={
        "provider_id": "meta",
        "model_id": "sam-3.1",
        "model_version": "sam-3.1",
        "prompt": "red square",
        "parameters_json": "{}",
        "destination": "https://api.meta.ai/v1",
        "usage_ceiling": _usage(usd_micros=2500, bytes_count=4096, frames=0, duration_ms=60_000),
    })
    ceilings = AggregateCeilings(
        per_requirement=_usage(usd_micros=2500, bytes_count=8192, duration_ms=60_000),
        per_case_mandate=_usage(usd_micros=5000, bytes_count=16384, duration_ms=120_000),
        deployment_account=_usage(usd_micros=10_000, bytes_count=32768, duration_ms=240_000),
    )
    retention = proposal.retention.model_copy(update={"destination": "https://api.meta.ai/v1"})
    proposal = type(proposal).model_validate({
        **proposal.model_dump(), "processing_plan": plan, "ceilings": ceilings,
        "retention": retention,
    })
    authorization = authorization.model_copy(update={"proposal_digest": canonical_record_digest(proposal)})
    gate = _MemoryGate()
    processor = MetaSamProcessor(
        api_key="secret-test-key",
        transport=lambda *args: (200, {"x-request-id": "req-coordinator"}, json.dumps(_response()).encode()),
    )
    source = type("ImageSource", (), {
        "capture": lambda self, request, attempt: AdapterResponse(
            payload=BytesIO(PNG), usage=ResourceUsage(usd_micros=0, bytes=len(PNG), frames=0, duration_ms=1)
        ),
    })()
    result = AcquisitionCoordinator(
        gate=gate,
        artifacts=_MemoryArtifacts(),
        source=source,
        processor=processor,
        clock=_FakeClock(),
    ).acquire(proposal, authorization, "fixture-proof")

    assert result.annotation is not None
    assert result.annotation.provider_id == "meta"
    assert result.annotation.is_empty is False
    assert result.annotation.usage.usd_micros == 2500
    assert result.evaluation is None
    assert gate.attempts["attempt-2"].provider_request_id == "req-coordinator"
    assert gate.attempts["attempt-2"].state == AttemptState.COMPLETED
