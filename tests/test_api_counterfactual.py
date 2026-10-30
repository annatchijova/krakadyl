"""Level 5 over HTTP: a hypothetical never leaks into the real case."""

import importlib

import pytest
from fastapi.testclient import TestClient

from krakadyl.acquisition_runtime import hash_token

H = {"Authorization": "Bearer token-c"}
GRANT_B = {"question": {"allowed_device": "device-B", "destination": "reviewer-authorized"},
           "deltas": [{"kind": "grant_resource", "value": "case-001/device-B"}]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.setenv("KRAKADYL_ENABLE_DEV_ROUTES", "1")
    monkeypatch.setenv("KRAKADYL_OPERATOR_TOKENS", f"investigator-C={hash_token('token-c')}")
    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_counterfactual_is_attributed_measured_and_listed(client):
    resp = client.post("/api/cases/case-001/counterfactuals", json=GRANT_B, headers=H)
    assert resp.status_code == 200, resp.text
    cf = resp.json()["counterfactual"]
    assert cf["hypothetical"] is True and cf["created_by"] == "investigator-C"
    assert cf["real"]["authority_state"] == "denied"
    assert cf["hypothetical_outcome"]["authority_state"] == "granted"
    assert [v["stale"] for v in client.get("/api/cases/case-001/counterfactuals").json()] == [False]


def test_a_hypothetical_never_changes_what_the_case_allows(client):
    before = client.get("/api/cases/case-001").json()
    cf = client.post("/api/cases/case-001/counterfactuals", headers=H, json={
        "question": {"allowed_device": "device-A", "destination": "court-registry"},
        "deltas": [{"kind": "grant_destination", "value": "court-registry"}],
    }).json()["counterfactual"]
    assert cf["hypothetical_outcome"]["verdict"] == "allowed"

    real = client.post("/api/cases/case-001/actions/prepare", json={
        "principal": "investigator-A", "destination": "court-registry"}).json()
    assert real["decision"]["verdict"] == "forbidden"
    after = client.get("/api/cases/case-001").json()
    assert after["mandate"] == before["mandate"]
    assert client.post("/api/cases/case-001/actions/execute", json={
        "principal": "investigator-A", "prepared_action_id": cf["counterfactual_id"]}).status_code == 404


def test_a_counterfactual_goes_stale_when_the_case_moves(client):
    client.post("/api/cases/case-001/counterfactuals", json=GRANT_B, headers=H)
    client.post("/api/dev/cases/case-001/tamper", json={"observation_id": "obs-a1"})
    assert [v["stale"] for v in client.get("/api/cases/case-001/counterfactuals").json()] == [True]


def test_needs_a_proven_operator_and_well_formed_assumptions(client):
    assert client.post("/api/cases/case-001/counterfactuals", json=GRANT_B).status_code == 401
    bad = {**GRANT_B, "deltas": [{"kind": "requirement_verified", "requirement_id": "nope"}]}
    assert client.post("/api/cases/case-001/counterfactuals", json=bad, headers=H).status_code == 409
    free_text = {**GRANT_B, "deltas": [{"kind": "assume_file_intact", "value": "obs-a1"}]}
    assert client.post("/api/cases/case-001/counterfactuals", json=free_text, headers=H).status_code == 422
