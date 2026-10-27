"""The HTTP API, walking the same Level 2 narrative as
demo/run_case_002_level2.py — but over real requests against the real
core, through a real (temp-file) SQLite store. No mocked decisions, no
mocked executor: a FastAPI TestClient still calls the exact same
krakadyl.core functions the rest of the test suite exercises.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_case_overview_shows_the_seeded_two_device_case(client):
    resp = client.get("/api/cases/case-001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mission"]["id"] == "case-001"
    assert body["mandate"]["resources"] == ["case-001/device-A"]
    sources = {e["observation"]["source"] for e in body["evidence"]}
    assert sources == {"device-A", "device-B"}
    device_b = next(e for e in body["evidence"] if e["observation"]["source"] == "device-B")
    assert device_b["in_mandate_scope"] is False


def test_unknown_case_is_404(client):
    assert client.get("/api/cases/nope").status_code == 404


def test_prepare_then_execute_happy_path(client):
    prep = client.post("/api/cases/case-001/actions/prepare", json={}).json()
    assert prep["decision"]["verdict"] == "allowed"
    assert prep["prepared"] is not None

    exe = client.post(
        "/api/cases/case-001/actions/execute",
        json={"prepared_action_id": prep["prepared"]["id"]},
    ).json()
    assert exe["receipt"]["executed"] is True
    assert exe["manifest"] is not None
    assert exe["manifest"]["excluded_devices"] == ["device-B"]


def test_full_level_2_narrative_tamper_catch_recover_execute(client):
    # 1. Prepare while everything is fine.
    prep = client.post("/api/cases/case-001/actions/prepare", json={}).json()
    assert prep["decision"]["verdict"] == "allowed"
    prepared_id = prep["prepared"]["id"]

    # 2. Tamper obs-a1 (dev-only simulation).
    client.post("/api/dev/cases/case-001/tamper", json={"observation_id": "obs-a1"})

    # 3. Execute the now-stale PreparedAction — must be caught, nothing published.
    exe = client.post(
        "/api/cases/case-001/actions/execute",
        json={"prepared_action_id": prepared_id},
    ).json()
    assert exe["receipt"]["executed"] is False
    assert exe["manifest"] is None

    # 4. Recover a still-legitimate route.
    rec = client.post("/api/cases/case-001/actions/recover", json={}).json()
    assert rec["attempted"] is True
    assert rec["excluded_resources"] == ["obs-a1"]
    assert rec["prepared"] is not None

    # 5. Execute the recovered action for real; manifest names the exclusion.
    exe2 = client.post(
        "/api/cases/case-001/actions/execute",
        json={"prepared_action_id": rec["prepared"]["id"]},
    ).json()
    assert exe2["receipt"]["executed"] is True
    assert exe2["manifest"]["excluded_resources"] == [
        {
            "observation_id": "obs-a1",
            "reason": "integrity check failed: file no longer matches the digest recorded at acquisition",
        }
    ]

    # 6. Activity feed recorded every step.
    events = client.get("/api/cases/case-001/activity").json()
    kinds = [e["kind"] for e in events]
    assert "prepared" in kinds
    assert "dev_tampered" in kinds
    assert "execution_blocked" in kinds
    assert "recovery_proposed" in kinds
    assert "executed" in kinds


def test_revoked_mandate_blocks_recovery_honestly(client):
    client.post("/api/dev/cases/case-001/revoke-mandate", json={"reason": "case reassigned"})
    rec = client.post("/api/cases/case-001/actions/recover", json={}).json()
    assert rec["attempted"] is False
    assert "no exclusion can" in rec["closed_reason"]


def test_hypothesis_flagged_after_requirement_becomes_unresolvable(client):
    before = client.get("/api/cases/case-001").json()
    hyp_before = next(h for h in before["hypotheses"] if h["hypothesis"]["id"] == "hyp-001")
    assert hyp_before["needs_review"] is False
    assert hyp_before["hypothesis"]["status"] == "accepted"

    client.post("/api/dev/cases/case-001/unresolve-hypothesis-requirement")

    after = client.get("/api/cases/case-001").json()
    hyp_after = next(h for h in after["hypotheses"] if h["hypothesis"]["id"] == "hyp-001")
    assert hyp_after["needs_review"] is True
    # Still ACCEPTED — needs_review and the prior decision are a
    # distinct fact, never collapsed into one status.
    assert hyp_after["hypothesis"]["status"] == "accepted"


def test_replay_is_refused_even_through_the_api(client):
    prep = client.post("/api/cases/case-001/actions/prepare", json={}).json()
    prepared_id = prep["prepared"]["id"]

    first = client.post(
        "/api/cases/case-001/actions/execute", json={"prepared_action_id": prepared_id}
    ).json()
    assert first["receipt"]["executed"] is True

    second = client.post(
        "/api/cases/case-001/actions/execute", json={"prepared_action_id": prepared_id}
    ).json()
    assert second["receipt"]["executed"] is False
    assert "replay" in second["receipt"]["observed_effect"]


def test_propose_with_muse_wires_a_real_adapter_call_through_the_real_pipeline(client, monkeypatch):
    """No network call: krakadyl.api.app.propose_action is monkeypatched
    to a fake, the same way tests/test_muse_adapter.py fakes the
    transport one layer down — this test is about the endpoint's own
    wiring (building summaries, persisting, the candidate still going
    through prepare_evidence_package unchanged), not about Muse itself.
    """
    import krakadyl.api.app as app_module
    from krakadyl.adapters.muse import ProposedActionCandidate

    def fake_propose_action(*, mission_summary, mandate_summary, case_summary, **kwargs):
        assert "device-A" in mandate_summary
        assert "obs-a1" in case_summary
        return ProposedActionCandidate(
            operation="package_export",
            allowed_device="device-A",
            destination="reviewer-authorized",
            reasoning="obs-a1 and obs-a2 are verified; package them for the reviewer.",
        )

    monkeypatch.setattr(app_module, "propose_action", fake_propose_action)

    resp = client.post("/api/cases/case-001/actions/propose-with-muse", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["muse_operation"] == "package_export"
    assert body["decision"]["verdict"] == "allowed"
    assert body["prepared"] is not None

    events = client.get("/api/cases/case-001/activity").json()
    assert any(e["kind"] == "muse_proposed" for e in events)


def test_propose_with_muse_surfaces_an_adapter_failure_as_502(client, monkeypatch):
    import krakadyl.api.app as app_module
    from krakadyl.adapters.muse import MuseAdapterError

    def failing_propose_action(**kwargs):
        raise MuseAdapterError("Muse response did not match the expected schema")

    monkeypatch.setattr(app_module, "propose_action", failing_propose_action)

    resp = client.post("/api/cases/case-001/actions/propose-with-muse", json={})
    assert resp.status_code == 502


def test_state_survives_reloading_the_app_against_the_same_data_dir(tmp_path, monkeypatch):
    data_dir = str(tmp_path / "api")
    monkeypatch.setenv("KRAKADYL_DATA_DIR", data_dir)

    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    client1 = TestClient(app_module.app)
    prep = client1.post("/api/cases/case-001/actions/prepare", json={}).json()
    assert prep["prepared"] is not None

    # Simulate a server restart: reload the module again against the
    # same KRAKADYL_DATA_DIR.
    importlib.reload(app_module)
    client2 = TestClient(app_module.app)
    fetched = client2.get(
        f"/api/cases/case-001/prepared/{prep['prepared']['id']}"
    ).json()
    assert fetched["prepared"]["id"] == prep["prepared"]["id"]
