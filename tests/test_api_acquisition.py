"""Level 3 over HTTP: the seeded case's open clock requirement walked
through proposal, authorization, capture, SAM (fake transport only),
evaluation, abstention and reconciliation — real store, real gate, real
coordinator, real filesystem repository.
"""

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from krakadyl.acquisition_runtime import AcquisitionRuntime, FilesystemArtifactRepository, hash_token
from krakadyl.adapters.sam import MetaSamProcessor

PNG = b"\x89PNG\r\n\x1a\n" + b"seeded-case clock photograph"
SAM_TEXT = "<0f>1<|box;x1=2;y1=3;x2=10;y2=8;w=32;h=24;c=0.91|><|mask;x=0;y=0;data=2,3,~!!!!M|>"
A = {"Authorization": "Bearer token-for-a"}
C = {"Authorization": "Bearer token-for-c"}
REQ = "req-device-a-clock"


class _FakeSam:
    def __init__(self):
        self.text, self.fail, self.calls = SAM_TEXT, False, 0

    def __call__(self, url, headers, body, timeout):
        self.calls += 1
        if self.fail:
            raise ConnectionResetError("synthetic reset after dispatch")
        response = {"id": "sam-1", "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": self.text}]}]}
        return 200, {"x-request-id": "sam-1"}, json.dumps(response).encode()


def _load(tmp_path, monkeypatch, tokens=True):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.delenv("KRAKADYL_ENABLE_SAM", raising=False)
    if tokens:
        monkeypatch.setenv(
            "KRAKADYL_OPERATOR_TOKENS",
            f"investigator-A={hash_token('token-for-a')};investigator-C={hash_token('token-for-c')}",
        )
    else:
        monkeypatch.delenv("KRAKADYL_OPERATOR_TOKENS", raising=False)
    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    return app_module


@pytest.fixture
def api(tmp_path, monkeypatch):
    app_module = _load(tmp_path, monkeypatch)
    sam = _FakeSam()
    app_module.acquisition = AcquisitionRuntime(
        store=app_module.store,
        credentials=app_module.acquisition.credentials,
        artifacts=FilesystemArtifactRepository(tmp_path / "api" / "acquired"),
        sam_processor=MetaSamProcessor(api_key="test-key", transport=sam),
    )
    return TestClient(app_module.app), sam


def _route(client):
    overview = client.get("/api/cases/case-001/acquisition").json()
    return next(r for r in overview["routes"] if r["requirement"]["id"] == REQ), overview


def _capture(client, headers=A, sam_prompt="clock display", content=PNG, content_type="image/png"):
    proposal = client.post(
        f"/api/cases/case-001/requirements/{REQ}/acquisition-proposals",
        json={"capture_instructions": "Photograph device-A's lock screen beside the reference clock.",
              "sam_prompt": sam_prompt},
        headers=headers,
    )
    assert proposal.status_code == 200, proposal.text
    grant = client.post(
        f"/api/cases/case-001/acquisition-proposals/{proposal.json()['id']}/authorize", headers=headers
    )
    assert grant.status_code == 200, grant.text
    return client.post(
        f"/api/cases/case-001/acquisition-authorizations/{grant.json()['id']}/capture",
        content=content, headers={**headers, "Content-Type": content_type},
    )


def _evaluate(client, workflow_id, headers, outcome="supports_requirement", revision=None):
    route, _ = _route(client)
    return client.post(
        f"/api/cases/case-001/acquisitions/{workflow_id}/evaluations",
        json={"expected_requirement_revision": revision or route["requirement_revision"],
              "criterion_id": "clock-within-one-minute", "criterion_version": "1",
              "outcome": outcome, "rationale": "Both clocks read 16:42."},
        headers=headers,
    )


def test_disabled_deployment_says_so_and_refuses_every_action(tmp_path, monkeypatch):
    client = TestClient(_load(tmp_path, monkeypatch, tokens=False).app)
    overview = client.get("/api/cases/case-001/acquisition").json()
    assert overview["enabled"] is False
    assert overview["routes"][0]["refusal"] == "acquisition is disabled in this deployment"
    resp = client.post(
        f"/api/cases/case-001/requirements/{REQ}/acquisition-proposals",
        json={"capture_instructions": "x"}, headers=A,
    )
    assert resp.status_code == 503


def test_seeded_clock_requirement_has_a_route(api):
    client, _ = api
    route, overview = _route(client)
    assert overview["enabled"] and overview["sam_enabled"]
    assert route["route"]["hypothesis_ids"] == ["hyp-002"]
    assert route["refusal"] is None


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic token-for-a"}])
def test_actions_require_a_proven_operator_token(api, headers):
    client, _ = api
    resp = client.post(
        f"/api/cases/case-001/requirements/{REQ}/acquisition-proposals",
        json={"capture_instructions": "x"}, headers=headers,
    )
    assert resp.status_code == 401


def test_full_lifecycle_over_http(api):
    client, sam = api
    captured = _capture(client)
    assert captured.status_code == 200, captured.text
    body = captured.json()
    workflow_id = body["workflow"]["workflow_id"]
    assert body["state"] == "completed" and body["evaluations"] == []
    assert sam.calls == 1

    image = client.get(f"/api/cases/case-001/acquisitions/{workflow_id}/observation")
    assert image.content == PNG and image.headers["content-type"] == "image/png"
    annotation = client.get(f"/api/cases/case-001/acquisitions/{workflow_id}/annotation").json()
    assert annotation["sidecar_status"] == "parsed"
    assert annotation["boxes"][0]["x1"] == 2 and annotation["frame_width"] == 32
    assert annotation["trust"].startswith("untrusted")

    route, _ = _route(client)
    assert route["requirement"]["resolved"] is False  # the annotation alone changed nothing

    evaluated = _evaluate(client, workflow_id, C)
    assert evaluated.status_code == 200, evaluated.text
    route, _ = _route(client)
    assert route["requirement"]["resolved"] is True
    assert route["requirement"]["responsibility"]["verified_by"] == "investigator-C"
    assert route["refusal"] == "requirement is already resolved"

    hypotheses = client.get("/api/cases/case-001").json()["hypotheses"]
    assert next(h for h in hypotheses if h["hypothesis"]["id"] == "hyp-002")["hypothesis"]["status"] == "proposed"
    kinds = [e["kind"] for e in client.get("/api/cases/case-001/activity").json()]
    for kind in ("acquisition_proposed", "acquisition_authorized", "acquisition_completed", "acquisition_evaluated"):
        assert kind in kinds


def test_content_type_must_match_the_bytes(api):
    client, sam = api
    resp = _capture(client, content=PNG, content_type="image/jpeg")
    assert resp.status_code == 415
    assert sam.calls == 0


def test_non_principal_cannot_capture_even_with_a_valid_token(api):
    client, sam = api
    resp = _capture(client, headers=C)
    assert resp.status_code == 409
    assert "scoped to 'investigator-A'" in resp.json()["detail"]
    assert client.get("/api/cases/case-001/acquisition").json()["history"] == []
    assert sam.calls == 0


def test_stale_evaluation_and_abstention_are_conflicts(api):
    client, _ = api
    workflow_id = _capture(client).json()["workflow"]["workflow_id"]
    assert _evaluate(client, workflow_id, C, revision="0" * 64).status_code == 409
    resp = client.post(
        f"/api/cases/case-001/requirements/{REQ}/abstain",
        json={"expected_requirement_revision": "0" * 64, "reason": "x"}, headers=A,
    )
    assert resp.status_code == 409


def test_non_discriminating_result_then_abstention(api):
    client, sam = api
    sam.text = ""
    workflow_id = _capture(client).json()["workflow"]["workflow_id"]
    assert client.get(f"/api/cases/case-001/acquisitions/{workflow_id}/annotation").json()["sidecar_status"] == "empty"
    assert _evaluate(client, workflow_id, C, outcome="no_discriminating_change").status_code == 200
    route, _ = _route(client)
    assert route["route"] is not None  # still open, another route remains possible

    closed = client.post(
        f"/api/cases/case-001/requirements/{REQ}/abstain",
        json={"expected_requirement_revision": route["requirement_revision"],
              "reason": "device-A powered off before a readable capture"},
        headers=A,
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["unresolvable"] is True
    flagged = client.get("/api/cases/case-001").json()["hypotheses"]
    hyp = next(h for h in flagged if h["hypothesis"]["id"] == "hyp-002")
    assert hyp["needs_review"] is True and "unresolvable" in hyp["review_reason"]


def test_unknown_outcome_is_visible_blocks_retry_and_is_reconciled_by_a_human(api):
    client, sam = api
    sam.fail = True
    resp = _capture(client)
    assert resp.status_code == 502
    history = client.get("/api/cases/case-001/acquisition").json()["history"]
    assert history[0]["state"] == "unknown"
    unknown_attempt = next(a for a in history[0]["attempts"] if a["state"] == "unknown_after_dispatch")

    sam.fail = False
    assert _capture(client).status_code == 409  # blocked while unknown
    assert sam.calls == 1

    reconciled = client.post(
        f"/api/cases/case-001/acquisition-attempts/{unknown_attempt['attempt']['attempt_id']}/reconcile",
        json={"disposition": "accepted_as_unknown", "rationale": "Provider console shows no record; accepting the spend as unknown."},
        headers=A,
    )
    assert reconciled.status_code == 200, reconciled.text
    assert _capture(client).status_code == 200
    assert sam.calls == 2


def test_dev_reset_clears_acquisition_records(api):
    client, _ = api
    _capture(client, sam_prompt=None)
    assert client.post("/api/dev/cases/case-001/reset").status_code == 200
    overview = client.get("/api/cases/case-001/acquisition").json()
    assert overview["history"] == [] and overview["proposals"] == []
    assert _capture(client, sam_prompt=None).status_code == 200
