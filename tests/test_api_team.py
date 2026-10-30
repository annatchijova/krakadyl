"""Level 4 over HTTP on the seeded case: a teammate disputes a verified
acquisition, the package is blocked as CONFLICTING until someone outside
the conflict resolves it, and the case is handed over between shifts."""

import importlib

import pytest
from fastapi.testclient import TestClient

from krakadyl.acquisition_runtime import hash_token

TOKENS = {f"investigator-{x}": f"token-{x.lower()}" for x in "ABCDE"}
H = {who: {"Authorization": f"Bearer {token}"} for who, token in TOKENS.items()}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.delenv("KRAKADYL_ENABLE_SAM", raising=False)
    monkeypatch.setenv("KRAKADYL_OPERATOR_TOKENS", ";".join(f"{i}={hash_token(t)}" for i, t in TOKENS.items()))
    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    return TestClient(app_module.app)


def _req(client, req_id):
    team = client.get("/api/cases/case-001/team").json()
    return next(r for r in team["requirements"] if r["requirement"]["id"] == req_id)


def _say(client, who, req_id, kind, **body):
    return client.post(
        f"/api/cases/case-001/requirements/{req_id}/team-records",
        json={"kind": kind, "statement": body.pop("statement", "statement"),
              "expected_requirement_revision": _req(client, req_id)["requirement_revision"], **body},
        headers=H[who],
    )


def _prepare(client):
    return client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()


def test_dispute_blocks_the_package_until_a_non_party_resolves_it(client):
    assert _prepare(client)["decision"]["verdict"] == "allowed"

    resp = _say(client, "investigator-B", "req-a1", "disputed", statement="obs-a1 on the share is truncated")
    assert resp.status_code == 200, resp.text
    [conflict] = _req(client, "req-a1")["open_conflicts"]
    evidence = {e["observation"]["id"]: e for e in client.get("/api/cases/case-001").json()["evidence"]}
    assert evidence["obs-a1"]["team_conflict"] is True and evidence["obs-a2"]["team_conflict"] is False

    blocked = _prepare(client)["decision"]
    assert blocked["verdict"] == "forbidden" and blocked["evidence_state"] == "conflicting"

    recovered = client.post("/api/cases/case-001/actions/recover", json={"principal": "investigator-A"}).json()
    assert recovered["excluded_resources"] == ["obs-a1"]

    resolve = {"refers_to": list(conflict["record_ids"]), "resolves_conflict_id": conflict["conflict_id"],
               "decision": "keep_current_state", "statement": "re-hashed obs-a1: intact"}
    # investigator-C verified req-a1 in the seed, so C is a party too.
    assert _say(client, "investigator-C", "req-a1", "resolution", **resolve).status_code == 409
    assert _say(client, "investigator-D", "req-a1", "resolution", **resolve).status_code == 200
    assert _prepare(client)["decision"]["verdict"] == "allowed"


def test_a_conflict_raised_between_prepare_and_execute_stops_execution(client):
    prepared = _prepare(client)["prepared"]
    _say(client, "investigator-B", "req-a2", "disputed", statement="obs-a2 copy differs")
    executed = client.post("/api/cases/case-001/actions/execute",
                           json={"principal": "investigator-A", "prepared_action_id": prepared["id"]}).json()
    assert executed["receipt"]["executed"] is False


def test_claims_cite_evidence_that_is_re_hashed(client):
    observation = next(e for e in client.get("/api/cases/case-001").json()["evidence"]
                       if e["observation"]["id"] == "obs-a1")["observation"]
    good = {"kind": "observation", "ref_id": "obs-a1", "digest": observation["digest"]}
    bad = {**good, "digest": "0" * 64}
    assert _say(client, "investigator-B", "req-device-a-clock", "reported_done", evidence_refs=[bad]).status_code == 409
    assert _say(client, "investigator-B", "req-device-a-clock", "reported_done", evidence_refs=[good]).status_code == 200
    assert _req(client, "req-device-a-clock")["requirement"]["responsibility"]["status"] == "reported_done"


def test_identity_comes_from_the_token_not_the_body(client):
    resp = client.post(
        "/api/cases/case-001/requirements/req-device-a-clock/team-records",
        json={"kind": "acknowledged", "statement": "x", "actor": "investigator-A",
              "expected_requirement_revision": _req(client, "req-device-a-clock")["requirement_revision"]},
        headers=H["investigator-B"],
    )
    assert resp.status_code == 409  # B is not the owner, whatever the body says
    assert client.post("/api/cases/case-001/requirements/req-device-a-clock/team-records",
                       json={"kind": "acknowledged", "statement": "x", "expected_requirement_revision": "0" * 64}
                       ).status_code == 401


def test_shift_handoff_round_trip(client):
    view = client.get("/api/cases/case-001/handoff").json()
    assert [i["requirement_id"] for i in view["handoff"]["not_acknowledged"]] == ["req-device-a-clock"]

    stale = client.post("/api/cases/case-001/handoffs", headers=H["investigator-A"], json={
        "to_actor": "investigator-E", "seen_state_digest": "0" * 64})
    assert stale.status_code == 409

    handed = client.post("/api/cases/case-001/handoffs", headers=H["investigator-A"], json={
        "to_actor": "investigator-E", "seen_state_digest": view["handoff"]["state_digest"],
        "transfer_requirement_ids": ["req-device-a-clock"], "note": "clock photo still needed before battery dies",
    })
    assert handed.status_code == 200, handed.text
    [handoff_id] = handed.json()["pending_for"]["investigator-E"]

    assert client.post(f"/api/cases/case-001/handoffs/{handoff_id}/accept", headers=H["investigator-B"]).status_code == 409
    accepted = client.post(f"/api/cases/case-001/handoffs/{handoff_id}/accept", headers=H["investigator-E"])
    assert accepted.status_code == 200
    assert accepted.json()["pending_for"] == {}
    owner = _req(client, "req-device-a-clock")["requirement"]["responsibility"]
    assert owner["owner"] == "investigator-E" and owner["status"] == "acknowledged"
    # Ownership moved; capture authority did not.
    mandate = client.get("/api/cases/case-001/acquisition").json()
    assert mandate["routes"][0]["route"]["mandate_id"] == "mandate-capture-001"
    kinds = [e["kind"] for e in client.get("/api/cases/case-001/activity").json()]
    assert "shift_handoff" in kinds and "shift_accepted" in kinds
