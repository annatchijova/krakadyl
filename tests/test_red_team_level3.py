"""Red team of the Level 3 case wiring (docs/red-team-level3-case-wiring.md).

Each test reproduces one finding against the code as first committed on
feat/level3-case-acquisition; each was observed failing before its fix.
"""

import pytest
from fastapi.testclient import TestClient

from krakadyl.core.acquisition import EvaluationOutcome, requirement_revision_digest
from krakadyl.core.evaluation import EvaluationRejected, abstain_requirement, record_evaluation
from krakadyl.core.models import EvidenceRequirement, TaskResponsibility, TaskStatus
from test_acquisition_runtime import CASE, TOKENS, _acquire, _current, _evaluate, _requirement, env  # noqa: F401
from test_api_acquisition import A, C, REQ, _capture, _load, api  # noqa: F401


# F1 — an evaluation must answer the question the capture was taken for.
def test_capture_for_one_question_cannot_resolve_a_reworded_requirement(env):
    store, runtime, _, _ = env
    result = _acquire(store, runtime)
    store.put(CASE, "requirement", _requirement(
        discriminating_question="Does device-A's clock show the correct date?",
    ), "2026-10-30T00:00:00+00:00")
    with pytest.raises(EvaluationRejected, match="different question"):
        _evaluate(store, result, "investigator-C", EvaluationOutcome.SUPPORTS_REQUIREMENT)
    assert _current(store).resolved is False


# F3 — evaluating is a use of the bytes; the bytes must still be the captured ones.
def test_evaluation_is_refused_when_the_stored_capture_no_longer_matches(api):
    client, _ = api
    workflow_id = _capture(client, sam_prompt=None).json()["workflow"]["workflow_id"]
    history = client.get("/api/cases/case-001/acquisition", headers=A).json()["history"]
    digest = history[0]["observation"]["digest"]
    import krakadyl.api.app as app_module

    path = app_module.DATA_DIR / "acquired" / "case-001" / "originals" / digest
    path.write_bytes(b"\x89PNG\r\n\x1a\nswapped after capture")
    route = next(r for r in client.get("/api/cases/case-001/acquisition").json()["routes"] if r["requirement"]["id"] == REQ)
    resp = client.post(
        f"/api/cases/case-001/acquisitions/{workflow_id}/evaluations",
        json={"expected_requirement_revision": route["requirement_revision"], "criterion_id": "c",
              "criterion_version": "1", "outcome": "supports_requirement", "rationale": "looks fine"},
        headers=C,
    )
    assert resp.status_code == 409
    assert "integrity" in resp.json()["detail"]


# F2 — reconciling an UNKNOWN attempt can refund budget and unblock the
# requirement; only the operator who authorized that workflow may do it.
def test_only_the_authorizer_can_reconcile_an_unknown_attempt(api):
    client, sam = api
    sam.fail = True
    assert _capture(client).status_code == 502
    history = client.get("/api/cases/case-001/acquisition").json()["history"]
    attempt = next(a for a in history[0]["attempts"] if a["state"] == "unknown_after_dispatch")
    resp = client.post(
        f"/api/cases/case-001/acquisition-attempts/{attempt['attempt']['attempt_id']}/reconcile",
        json={"disposition": "confirmed_not_dispatched", "rationale": "trust me"},
        headers=C,
    )
    assert resp.status_code == 409
    assert client.get("/api/cases/case-001/acquisition").json()["history"][0]["state"] == "unknown"


# F6 — a capture that completed must stay evaluable after its SAM phase
# was reconciled; otherwise volatile evidence already preserved is lost.
def test_completed_capture_stays_evaluable_after_processor_reconciliation(api):
    client, sam = api
    sam.fail = True
    _capture(client)
    history = client.get("/api/cases/case-001/acquisition").json()["history"]
    workflow_id = history[0]["workflow"]["workflow_id"]
    attempt = next(a for a in history[0]["attempts"] if a["state"] == "unknown_after_dispatch")
    assert client.post(
        f"/api/cases/case-001/acquisition-attempts/{attempt['attempt']['attempt_id']}/reconcile",
        json={"disposition": "accepted_as_unknown", "rationale": "provider console unavailable"},
        headers=A,
    ).status_code == 200
    route = next(r for r in client.get("/api/cases/case-001/acquisition").json()["routes"] if r["requirement"]["id"] == REQ)
    resp = client.post(
        f"/api/cases/case-001/acquisitions/{workflow_id}/evaluations",
        json={"expected_requirement_revision": route["requirement_revision"], "criterion_id": "c",
              "criterion_version": "1", "outcome": "supports_requirement", "rationale": "16:42 on both"},
        headers=C,
    )
    assert resp.status_code == 200, resp.text
    evaluation = resp.json()["evaluations"][0]
    assert evaluation["annotation_id"] is None


# F4 — raw captured evidence and model output are not served anonymously.
def test_captured_bytes_and_annotation_require_an_operator_token(api):
    client, _ = api
    workflow_id = _capture(client).json()["workflow"]["workflow_id"]
    for kind in ("observation", "annotation"):
        assert client.get(f"/api/cases/case-001/acquisitions/{workflow_id}/{kind}").status_code == 401
        assert client.get(f"/api/cases/case-001/acquisitions/{workflow_id}/{kind}", headers=C).status_code == 200


# F5 — an anonymous dev reset must not wipe the acquisition audit trail.
def test_dev_reset_needs_an_operator_token_when_acquisition_is_enabled(api):
    client, _ = api
    _capture(client, sam_prompt=None)
    assert client.post("/api/dev/cases/case-001/reset").status_code == 401
    assert len(client.get("/api/cases/case-001/acquisition").json()["history"]) == 1
    assert client.post("/api/dev/cases/case-001/reset", headers=A).status_code == 200


def test_dev_reset_stays_anonymous_when_acquisition_is_disabled(tmp_path, monkeypatch):
    client = TestClient(_load(tmp_path, monkeypatch, tokens=False).app)
    assert client.post("/api/dev/cases/case-001/reset").status_code == 200


# F7 — closing evidence as unobtainable is the requirement owner's call.
def test_only_the_requirement_owner_can_abstain(env):
    store, runtime, sam, _ = env
    with pytest.raises(EvaluationRejected, match="owner"):
        abstain_requirement(
            store, case_id=CASE, requirement_id="req-device-a-clock",
            expected_requirement_revision=requirement_revision_digest(_current(store)),
            actor_identity="investigator-C", reason="not my case but closing it", now=_now(),
        )


# F8 — a later self-evaluation must not erase who claimed it first.
def test_self_evaluation_keeps_the_earlier_claimant_on_record(env):
    store, runtime, _, _ = env
    store.put(CASE, "requirement", _requirement(responsibility=TaskResponsibility(
        owner="investigator-A", status=TaskStatus.REPORTED_DONE, reported_done_by="investigator-B",
    )), "2026-10-30T00:00:00+00:00")
    result = _acquire(store, runtime)
    _, after = _evaluate(store, result, "investigator-A", EvaluationOutcome.SUPPORTS_REQUIREMENT)
    assert after.responsibility.status == TaskStatus.REPORTED_DONE
    assert after.responsibility.reported_done_by == "investigator-B"


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
