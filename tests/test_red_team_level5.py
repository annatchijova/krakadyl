"""Red team of Level 5 counterfactuals (docs/red-team-level5-comparable-routes.md).

Each test reproduces one finding against commit 5a57d17 and was observed
failing before its fix."""

import importlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from krakadyl.acquisition_runtime import hash_token

H = {"Authorization": "Bearer token-c"}
QUESTION = {"allowed_device": "device-A", "destination": "reviewer-authorized"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.setenv("KRAKADYL_OPERATOR_TOKENS", f"investigator-C={hash_token('token-c')}")
    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    return app_module, TestClient(app_module.app)


# F1 — time alone can change the real verdict (a mandate expires); a
# counterfactual whose "real" side no longer holds must read as stale.
def test_a_counterfactual_goes_stale_when_time_changes_the_real_verdict(api, monkeypatch):
    app_module, client = api
    mandate_end = app_module._current_mandate("case-001").valid_until
    monkeypatch.setattr(app_module, "now", lambda: mandate_end - timedelta(hours=1))
    created = client.post("/api/cases/case-001/counterfactuals", headers=H, json={
        "question": QUESTION, "deltas": [{"kind": "grant_destination", "value": "court-registry"}]})
    assert created.json()["counterfactual"]["real"]["verdict"] == "allowed"

    monkeypatch.setattr(app_module, "now", lambda: mandate_end + timedelta(hours=1))
    assert client.post("/api/cases/case-001/actions/prepare",
                       json={"principal": "investigator-A"}).json()["decision"]["verdict"] == "forbidden"
    [view] = client.get("/api/cases/case-001/counterfactuals").json()
    assert view["stale"] is True


# F2 — the shared activity log must not read like a real verdict change.
def test_activity_entry_is_unmistakably_hypothetical(api):
    _, client = api
    client.post("/api/cases/case-001/counterfactuals", headers=H, json={
        "question": {"allowed_device": "device-B", "destination": "reviewer-authorized"},
        "deltas": [{"kind": "grant_resource", "value": "case-001/device-B"}]})
    entry = next(e for e in client.get("/api/cases/case-001/activity").json() if e["kind"] == "counterfactual_evaluated")
    assert entry["summary"].startswith("[HYPOTHETICAL]")
    assert "would become" not in entry["summary"]


# F1, isolated: nothing in the inputs changes, only the clock. The input
# digest cannot see that, so staleness must also re-check the real outcome.
def test_staleness_sees_time_even_when_no_input_changed(tmp_path):
    from krakadyl.core.counterfactual import Delta, DeltaKind, Question, base_state_digest, evaluate_counterfactual, is_stale
    from test_counterfactual import _inputs
    from test_executor import NOW, _mandate, _observation, _verified_requirement

    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"one")]
    case = (observations, {"obs-a1": raw / "a1.jpg"}, [_verified_requirement("req-a1", "obs-a1")])
    inputs = _inputs(case, mandate=_mandate(valid_until=NOW + timedelta(hours=1)))
    question = Question(allowed_device="device-A", destination="reviewer-authorized")
    cf = evaluate_counterfactual(inputs, question, (Delta(kind=DeltaKind.GRANT_DESTINATION, value="x"),),
                                 created_by="investigator-C", now=NOW)
    later = NOW + timedelta(hours=2)
    assert base_state_digest(inputs, question) == cf.base_state_digest  # the gap: digest is blind to time
    assert is_stale(inputs, cf, now=NOW) is False
    assert is_stale(inputs, cf, now=later) is True
