"""The HTTP API, walking the same Level 2 narrative as
demo/run_case_002_level2.py — but over real requests against the real
core, through a real (temp-file) SQLite store. No mocked decisions, no
mocked executor: a FastAPI TestClient still calls the exact same
krakadyl.core functions the rest of the test suite exercises.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from krakadyl.acquisition_runtime import hash_token


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.setenv("KRAKADYL_ENABLE_DEV_ROUTES", "1")
    monkeypatch.setenv(
        "KRAKADYL_OPERATOR_TOKENS",
        f"investigator-A={hash_token('token-a')};investigator-C={hash_token('token-c')}",
    )
    monkeypatch.delenv("KRAKADYL_MUSE_RATE_LIMIT_PER_MINUTE", raising=False)
    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    client = TestClient(app_module.app)
    client.headers.update({"Authorization": "Bearer token-a"})
    return client


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


def test_observation_invalidation_requires_authentication_and_records_actor(client):
    anonymous = client.post(
        "/api/cases/case-001/observations/obs-a1/invalidate",
        headers={"Authorization": ""},
        json={"reason": "primary source provenance was disproved"},
    )
    assert anonymous.status_code == 401

    response = client.post(
        "/api/cases/case-001/observations/obs-a1/invalidate",
        json={"reason": "primary source provenance was disproved"},
    )
    assert response.status_code == 200
    assert response.json()["invalidated"] is True
    assert response.json()["invalidation_reason"] == "primary source provenance was disproved"

    overview = client.get("/api/cases/case-001").json()
    invalidated_item = next(item for item in overview["evidence"] if item["observation"]["id"] == "obs-a1")
    assert invalidated_item["independently_verified"] is False

    import krakadyl.api.app as app_module
    _, _, case_summary = app_module._case_summaries("case-001")
    assert "obs-a1 (device-A): integrity ok, NOT independently verified" in case_summary

    events = client.get("/api/cases/case-001/activity").json()
    invalidation = next(event for event in events if event["kind"] == "observation_invalidated")
    assert invalidation["detail"]["actor_identity"] == "investigator-A"


def test_observation_invalidation_cannot_cross_case_or_repeat(client):
    missing = client.post(
        "/api/cases/no-such-case/observations/obs-a1/invalidate",
        json={"reason": "not applicable"},
    )
    assert missing.status_code == 404

    first = client.post(
        "/api/cases/case-001/observations/obs-a1/invalidate",
        json={"reason": "source was disproved"},
    )
    assert first.status_code == 200
    repeated = client.post(
        "/api/cases/case-001/observations/obs-a1/invalidate",
        json={"reason": "second reason"},
    )
    assert repeated.status_code == 409


def test_unknown_case_is_404(client):
    assert client.get("/api/cases/nope").status_code == 404


def test_case_reads_require_a_bearer_operator(client):
    import krakadyl.api.app as app_module

    anonymous = TestClient(app_module.app)
    response = anonymous.get("/api/cases/case-001")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", [
    "/api/cases/case-001/activity",
    "/api/cases/case-001/acquisition",
    "/api/cases/case-001/team",
    "/api/cases/case-001/handoff",
    "/api/cases/case-001/counterfactuals",
])
def test_case_metadata_surface_requires_a_bearer_operator(client, path):
    import krakadyl.api.app as app_module

    response = TestClient(app_module.app).get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path, payload", [
    ("/api/cases/{case_id}/actions/prepare", {}),
    ("/api/cases/{case_id}/actions/propose-with-muse", {}),
    ("/api/cases/{case_id}/analyze-note", {"note_text": "x"}),
    ("/api/cases/{case_id}/actions/recover", {}),
])
def test_anonymous_actions_do_not_reveal_case_existence(client, path, payload):
    headers = {"Authorization": ""}
    existing = client.post(path.format(case_id="case-001"), headers=headers, json=payload)
    missing = client.post(path.format(case_id="does-not-exist"), headers=headers, json=payload)
    assert existing.status_code == 401
    assert missing.status_code == 401


def test_bearer_identity_is_sufficient_without_a_principal_body(client):
    response = client.post("/api/cases/case-001/actions/prepare", json={})
    assert response.status_code == 200


def test_action_identity_is_bound_to_the_bearer_operator(client):
    response = client.post(
        "/api/cases/case-001/actions/prepare",
        json={"principal": "investigator-C"},
    )
    assert response.status_code == 403
    assert "authenticated operator" in response.json()["detail"]


def test_non_principal_operator_cannot_use_the_mandate(client):
    response = client.post(
        "/api/cases/case-001/actions/prepare",
        headers={"Authorization": "Bearer token-c"},
        json={"principal": "investigator-C"},
    )
    assert response.status_code == 403
    assert "mandate is scoped" in response.json()["detail"]


def test_non_principal_operator_cannot_probe_prepared_action_ids(client):
    prepared = client.post("/api/cases/case-001/actions/prepare", json={}).json()["prepared"]
    for prepared_action_id in (prepared["id"], "prepared-does-not-exist"):
        response = client.post(
            "/api/cases/case-001/actions/execute",
            headers={"Authorization": "Bearer token-c"},
            json={"prepared_action_id": prepared_action_id},
        )
        assert response.status_code == 403
        assert "mandate is scoped" in response.json()["detail"]


def test_prepare_then_execute_happy_path(client):
    prep = client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    assert prep["decision"]["verdict"] == "allowed"
    assert prep["prepared"] is not None

    exe = client.post(
        "/api/cases/case-001/actions/execute",
        json={"principal": "investigator-A", "prepared_action_id": prep["prepared"]["id"]},
    ).json()
    assert exe["receipt"]["executed"] is True
    assert exe["manifest"] is not None
    assert exe["manifest"]["excluded_devices"] == ["device-B"]


def test_api_execution_receipts_continue_the_case_chain(client):
    first_prep = client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    first = client.post(
        "/api/cases/case-001/actions/execute",
        json={"principal": "investigator-A", "prepared_action_id": first_prep["prepared"]["id"]},
    ).json()["receipt"]
    assert first["executed"] is True

    second_prep = client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    second = client.post(
        "/api/cases/case-001/actions/execute",
        json={"principal": "investigator-A", "prepared_action_id": second_prep["prepared"]["id"]},
    ).json()["receipt"]

    assert second["executed"] is True
    assert second["prev_hash"] == first["hash"]


def test_prepare_rolls_back_result_when_activity_event_cannot_be_written(client):
    import sqlite3
    import krakadyl.api.app as app_module

    app_module.store.atomic_write(lambda connection: connection.execute(
        "CREATE TRIGGER fail_prepared_event BEFORE INSERT ON events "
        "WHEN NEW.kind='prepared' BEGIN SELECT RAISE(ABORT, 'activity unavailable'); END"
    ))

    with pytest.raises(sqlite3.IntegrityError, match="activity unavailable"):
        app_module.prepare(
            "case-001",
            app_module.PrepareRequest(principal="investigator-A"),
            authorization="Bearer token-a",
        )

    assert app_module.store.list("case-001", "proposed_action", app_module.ProposedAction) == []
    assert app_module.store.list("case-001", "decision", app_module.Decision) == []
    assert app_module.store.list("case-001", "prepared_action", app_module.PreparedAction) == []


def test_full_level_2_narrative_tamper_catch_recover_execute(client):
    # 1. Prepare while everything is fine.
    prep = client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    assert prep["decision"]["verdict"] == "allowed"
    prepared_id = prep["prepared"]["id"]

    # 2. Tamper obs-a1 (dev-only simulation).
    client.post("/api/dev/cases/case-001/tamper", json={"observation_id": "obs-a1"})

    # 3. Execute the now-stale PreparedAction — must be caught, nothing published.
    exe = client.post(
        "/api/cases/case-001/actions/execute",
        json={"principal": "investigator-A", "prepared_action_id": prepared_id},
    ).json()
    assert exe["receipt"]["executed"] is False
    assert exe["manifest"] is None

    # 4. Recover a still-legitimate route.
    rec = client.post("/api/cases/case-001/actions/recover", json={"principal": "investigator-A"}).json()
    assert rec["attempted"] is True
    assert rec["excluded_resources"] == ["obs-a1"]
    assert rec["prepared"] is not None

    # 5. Execute the recovered action for real; manifest names the exclusion.
    exe2 = client.post(
        "/api/cases/case-001/actions/execute",
        json={"principal": "investigator-A", "prepared_action_id": rec["prepared"]["id"]},
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
    rec = client.post("/api/cases/case-001/actions/recover", json={"principal": "investigator-A"}).json()
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
    import krakadyl.api.app as app_module

    prep = client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    prepared_id = prep["prepared"]["id"]

    first = client.post(
        "/api/cases/case-001/actions/execute", json={"principal": "investigator-A", "prepared_action_id": prepared_id}
    ).json()
    assert first["receipt"]["executed"] is True

    second = client.post(
        "/api/cases/case-001/actions/execute", json={"principal": "investigator-A", "prepared_action_id": prepared_id}
    ).json()
    assert second["receipt"]["executed"] is False
    assert "replay" in second["receipt"]["observed_effect"]
    persisted = app_module.store.get("case-001", "receipt", first["receipt"]["id"], app_module.Receipt)
    assert persisted.executed is True


def test_execute_reloads_mandate_after_authorization_before_dispatch(client, monkeypatch):
    """A mandate revoked after initial authentication must block dispatch."""
    import krakadyl.api.app as app_module
    from krakadyl.core.models import Mandate

    prep = client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    prepared_id = prep["prepared"]["id"]
    initial = app_module._current_mandate("case-001")
    revoked = Mandate(
        **{
            **initial.model_dump(),
            "revoked": True,
            "revoked_reason": "revoked between authentication and dispatch",
            "revision": str(int(initial.revision) + 1),
        }
    )
    reads = []

    def mandate_transition(case_id):
        reads.append(case_id)
        return initial if len(reads) == 1 else revoked

    monkeypatch.setattr(app_module, "_current_mandate", mandate_transition)
    response = client.post(
        "/api/cases/case-001/actions/execute",
        json={"principal": "investigator-A", "prepared_action_id": prepared_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["receipt"]["executed"] is False
    assert "revoked" in body["receipt"]["observed_effect"]
    assert len(reads) == 2


def test_execution_failure_after_nonce_claim_burns_prepared_action(client, monkeypatch):
    import krakadyl.api.app as app_module

    prep = client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    prepared_id = prep["prepared"]["id"]

    def fail_after_claim(**kwargs):
        raise RuntimeError("simulated executor interruption")

    monkeypatch.setattr(app_module, "execute_prepared_action", fail_after_claim)
    with pytest.raises(RuntimeError, match="simulated executor interruption"):
        app_module.execute(
            "case-001",
            app_module.ExecuteRequest(principal="investigator-A", prepared_action_id=prepared_id),
            authorization="Bearer token-a",
        )

    monkeypatch.undo()
    retry = app_module.execute(
        "case-001",
        app_module.ExecuteRequest(principal="investigator-A", prepared_action_id=prepared_id),
        authorization="Bearer token-a",
    )
    assert retry.receipt.executed is False
    assert "claimed by a prior execution attempt" in retry.receipt.observed_effect


def test_nonce_claim_storage_error_never_reaches_executor(client, monkeypatch):
    import sqlite3

    import krakadyl.api.app as app_module

    prep = client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    called = []
    monkeypatch.setattr(
        app_module.store,
        "claim_nonce",
        lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("database unavailable")),
    )
    monkeypatch.setattr(app_module, "execute_prepared_action", lambda **kwargs: called.append(kwargs))

    with pytest.raises(sqlite3.OperationalError, match="database unavailable"):
        app_module.execute(
            "case-001",
            app_module.ExecuteRequest(principal="investigator-A", prepared_action_id=prep["prepared"]["id"]),
                authorization="Bearer token-a",
        )
    assert called == []


def test_concurrent_execution_claims_nonce_once_and_preserves_success_receipt(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    import krakadyl.api.app as app_module

    prep = client.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    prepared_id = prep["prepared"]["id"]
    claim_barrier = Barrier(2)
    original_execute = app_module.execute_prepared_action
    original_claim = app_module.store.claim_nonce
    effects = []

    def synchronized_claim(*args):
        claim_barrier.wait(timeout=5)
        return original_claim(*args)

    def synchronized_execute(**kwargs):
        if kwargs["prepared"].nonce not in kwargs["consumed_nonces"]:
            effects.append(kwargs["prepared"].nonce)
        return original_execute(**kwargs)

    monkeypatch.setattr(app_module, "execute_prepared_action", synchronized_execute)
    monkeypatch.setattr(app_module.store, "claim_nonce", synchronized_claim)
    request = lambda: app_module.execute(
        "case-001",
        app_module.ExecuteRequest(principal="investigator-A", prepared_action_id=prepared_id),
        authorization="Bearer token-a",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: request(), range(2)))

    receipts = [response.receipt.model_dump() for response in responses]
    assert sorted(receipt["executed"] for receipt in receipts) == [False, True]
    assert len(effects) == 1
    assert "claimed" in next(r["observed_effect"] for r in receipts if not r["executed"])

    persisted = app_module.store.get("case-001", "receipt", receipts[0]["id"], app_module.Receipt)
    assert persisted.executed is True


def test_dev_tamper_rejects_a_path_traversal_observation_id(client):
    """Found by red-team review: observation_file_path() interpolates
    observation_id into a path unsanitized, so a crafted id containing
    '../' resolves outside the case's data directory (confirmed by
    reading the resolved path). Requiring the id to already be a known
    observation of this case closes that off, rather than trying to
    blocklist '../' and similar patterns one at a time.
    """
    resp = client.post(
        "/api/dev/cases/case-001/tamper",
        json={"observation_id": "../../../../tmp/evil"},
    )
    assert resp.status_code == 404


def test_dev_routes_are_absent_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.setenv("KRAKADYL_ENABLE_DEV_ROUTES", "0")
    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    try:
        disabled_client = TestClient(app_module.app)
        resp = disabled_client.post(
            "/api/dev/cases/case-001/tamper", json={"observation_id": "obs-a1"}
        )
        assert resp.status_code == 404
    finally:
        # Leave the module enabled again for every other test in this
        # file — they import the same cached module object.
        monkeypatch.setenv("KRAKADYL_ENABLE_DEV_ROUTES", "1")
        importlib.reload(app_module)


def test_dev_routes_are_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.delenv("KRAKADYL_ENABLE_DEV_ROUTES", raising=False)
    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    assert TestClient(app_module.app).post(
        "/api/dev/cases/case-001/tamper", json={"observation_id": "obs-a1"}
    ).status_code == 404


def test_analyze_note_returns_typed_signals_never_touching_case_state(client, monkeypatch):
    """No model load: krakadyl.api.app.analyze_handoff_note is
    monkeypatched, the same pattern as the Muse/Laya adapter tests one
    layer down. This test is about the endpoint's own wiring — identity
    check, event logging, and that nothing here mutates evidence or
    hypotheses — not about Laya's classification itself.
    """
    import krakadyl.api.app as app_module
    from krakadyl.adapters.laya import LayaSignals

    def fake_analyze(note_text: str) -> LayaSignals:
        assert "handoff" in note_text
        return LayaSignals(
            claims_independent_verification=0.1,
            claims_task_complete=0.95,
            urgency=0.3,
            raw={"routing": {"model": "fake"}},
        )

    monkeypatch.setattr(app_module, "analyze_handoff_note", fake_analyze)

    before = client.get("/api/cases/case-001").json()

    resp = client.post(
        "/api/cases/case-001/analyze-note",
        json={"principal": "investigator-A", "note_text": "handoff: obs-a1 done, nobody else checked"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["claims_independent_verification"] == pytest.approx(0.1)
    assert body["claims_task_complete"] == pytest.approx(0.95)

    after = client.get("/api/cases/case-001").json()
    assert before["evidence"] == after["evidence"]
    assert before["hypotheses"] == after["hypotheses"]

    events = client.get("/api/cases/case-001/activity").json()
    assert any(e["kind"] == "laya_signal" for e in events)


def test_analyze_note_surfaces_adapter_failure_as_503(client, monkeypatch):
    import krakadyl.api.app as app_module
    from krakadyl.adapters.laya import LayaAdapterError

    def failing_analyze(note_text: str):
        raise LayaAdapterError("the 'laya' package is not installed")

    monkeypatch.setattr(app_module, "analyze_handoff_note", failing_analyze)

    resp = client.post(
        "/api/cases/case-001/analyze-note",
        json={"principal": "investigator-A", "note_text": "anything"},
    )
    assert resp.status_code == 503


def test_analyze_note_requires_the_right_principal(client):
    resp = client.post(
        "/api/cases/case-001/analyze-note",
        json={"principal": "someone-else", "note_text": "anything"},
    )
    assert resp.status_code == 403


def test_analyze_note_has_a_bounded_input_contract():
    import krakadyl.api.app as app_module
    from pydantic import ValidationError

    assert len(app_module.AnalyzeNoteRequest(note_text="x" * 4000).note_text) == 4000
    with pytest.raises(ValidationError):
        app_module.AnalyzeNoteRequest(note_text="x" * 4001)


def test_wrong_principal_is_rejected_on_every_action_endpoint(client):
    """The bearer token is authoritative; a legacy body principal is only
    accepted when it matches the authenticated operator.
    """
    assert (
        client.post(
            "/api/cases/case-001/actions/prepare", json={"principal": "someone-else"}
        ).status_code
        == 403
    )
    assert client.post("/api/cases/case-001/actions/prepare", json={}).status_code == 200

    assert (
        client.post(
            "/api/cases/case-001/actions/recover", json={"principal": "someone-else"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/cases/case-001/actions/propose-with-muse", json={"principal": "someone-else"}
        ).status_code
        == 403
    )

    prep = client.post(
        "/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}
    ).json()
    assert (
        client.post(
            "/api/cases/case-001/actions/execute",
            json={"principal": "someone-else", "prepared_action_id": prep["prepared"]["id"]},
        ).status_code
        == 403
    )


def test_propose_with_muse_rate_limit_rejects_n_plus_one_before_summary_or_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.setenv(
        "KRAKADYL_OPERATOR_TOKENS",
        f"investigator-A={hash_token('token-a')}",
    )
    monkeypatch.setenv("KRAKADYL_MUSE_RATE_LIMIT_PER_MINUTE", "2")
    import krakadyl.api.app as app_module
    from krakadyl.adapters.muse import ProposedActionCandidate

    importlib.reload(app_module)
    adapter_calls = 0
    summary_calls = 0
    real_case_summaries = app_module._case_summaries

    def counted_case_summaries(case_id: str):
        nonlocal summary_calls
        summary_calls += 1
        return real_case_summaries(case_id)

    def fake_propose_action(**kwargs):
        nonlocal adapter_calls
        adapter_calls += 1
        return ProposedActionCandidate(
            operation="package_export",
            allowed_device="device-A",
            destination="reviewer-authorized",
            reasoning="bounded fake response",
        )

    monkeypatch.setattr(app_module, "_case_summaries", counted_case_summaries)
    monkeypatch.setattr(app_module, "propose_action", fake_propose_action)
    limited_client = TestClient(app_module.app)
    limited_client.headers.update({"Authorization": "Bearer token-a"})

    for _ in range(2):
        response = limited_client.post(
            "/api/cases/case-001/actions/propose-with-muse",
            json={"principal": "investigator-A"},
        )
        assert response.status_code == 200

    blocked = limited_client.post(
        "/api/cases/case-001/actions/propose-with-muse",
        json={"principal": "investigator-A"},
    )
    assert blocked.status_code == 429
    assert "per server process" in blocked.json()["detail"]
    assert adapter_calls == 2
    assert summary_calls == 2


def test_muse_rate_limiter_admission_is_atomic_across_threads():
    from threading import Barrier, Lock, Thread

    from fastapi import HTTPException

    import krakadyl.api.app as app_module

    limiter = app_module._MuseRateLimiter(2, clock=lambda: 100.0)
    barrier = Barrier(6)
    statuses = []
    statuses_lock = Lock()

    def attempt() -> None:
        barrier.wait()
        try:
            limiter.acquire()
        except HTTPException as exc:
            status = exc.status_code
        else:
            status = 200
        with statuses_lock:
            statuses.append(status)

    threads = [Thread(target=attempt) for _ in range(5)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert statuses.count(200) == 2
    assert statuses.count(429) == 3


def test_muse_rate_limiter_uses_its_lock_for_admission():
    from threading import Event, Thread

    import krakadyl.api.app as app_module

    limiter = app_module._MuseRateLimiter(1, clock=lambda: 100.0)
    completed = Event()

    def attempt() -> None:
        limiter.acquire()
        completed.set()

    limiter._lock.acquire()
    thread = Thread(target=attempt)
    try:
        thread.start()
        assert completed.wait(0.05) is False
    finally:
        limiter._lock.release()
    assert completed.wait(1) is True
    thread.join(timeout=1)


def test_failed_muse_call_still_consumes_rate_limit_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.setenv(
        "KRAKADYL_OPERATOR_TOKENS",
        f"investigator-A={hash_token('token-a')}",
    )
    monkeypatch.setenv("KRAKADYL_MUSE_RATE_LIMIT_PER_MINUTE", "1")
    import krakadyl.api.app as app_module
    from krakadyl.adapters.muse import MuseAdapterError

    importlib.reload(app_module)
    adapter_calls = 0

    def failing_propose_action(**kwargs):
        nonlocal adapter_calls
        adapter_calls += 1
        raise MuseAdapterError("failure after the external call was attempted")

    monkeypatch.setattr(app_module, "propose_action", failing_propose_action)
    limited_client = TestClient(app_module.app)
    limited_client.headers.update({"Authorization": "Bearer token-a"})

    first = limited_client.post(
        "/api/cases/case-001/actions/propose-with-muse",
        json={"principal": "investigator-A"},
    )
    second = limited_client.post(
        "/api/cases/case-001/actions/propose-with-muse",
        json={"principal": "investigator-A"},
    )

    assert first.status_code == 502
    assert second.status_code == 429
    assert adapter_calls == 1


def test_zero_muse_rate_limit_is_a_kill_switch_before_summary_or_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKADYL_DATA_DIR", str(tmp_path / "api"))
    monkeypatch.setenv(
        "KRAKADYL_OPERATOR_TOKENS",
        f"investigator-A={hash_token('token-a')}",
    )
    monkeypatch.setenv("KRAKADYL_MUSE_RATE_LIMIT_PER_MINUTE", "0")
    import krakadyl.api.app as app_module

    importlib.reload(app_module)

    def must_not_run(*args, **kwargs):
        pytest.fail("rate-limited requests must stop before summaries and Muse")

    monkeypatch.setattr(app_module, "_case_summaries", must_not_run)
    monkeypatch.setattr(app_module, "propose_action", must_not_run)
    limited_client = TestClient(app_module.app)
    limited_client.headers.update({"Authorization": "Bearer token-a"})

    response = limited_client.post(
        "/api/cases/case-001/actions/propose-with-muse",
        json={"principal": "investigator-A"},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


@pytest.mark.parametrize("raw_limit", ["-1", "not-an-integer"])
def test_invalid_muse_rate_limit_configuration_is_rejected(monkeypatch, raw_limit):
    import krakadyl.api.app as app_module

    monkeypatch.setenv("KRAKADYL_MUSE_RATE_LIMIT_PER_MINUTE", raw_limit)
    with pytest.raises(RuntimeError, match="must be a non-negative integer"):
        app_module._muse_rate_limit_from_environment()


def test_muse_rate_limit_capacity_returns_when_the_window_expires():
    from fastapi import HTTPException

    import krakadyl.api.app as app_module

    current = [0.0]
    limiter = app_module._MuseRateLimiter(1, clock=lambda: current[0])
    limiter.acquire()

    current[0] = 59.999
    with pytest.raises(HTTPException) as blocked:
        limiter.acquire()
    assert blocked.value.status_code == 429
    assert blocked.value.headers["Retry-After"] == "1"

    current[0] = 60.0
    limiter.acquire()


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

    resp = client.post("/api/cases/case-001/actions/propose-with-muse", json={"principal": "investigator-A"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["muse_operation"] == "package_export"
    assert body["decision"]["verdict"] == "allowed"
    assert body["prepared"] is not None

    events = client.get("/api/cases/case-001/activity").json()
    assert any(e["kind"] == "muse_proposed" for e in events)


def test_propose_with_muse_revalidates_mandate_after_external_call(client, monkeypatch):
    import krakadyl.api.app as app_module
    from krakadyl.adapters.muse import ProposedActionCandidate
    from krakadyl.core.models import Mandate

    def revoke_during_call(*, mission_summary, mandate_summary, case_summary, **kwargs):
        current = app_module._current_mandate("case-001")
        revoked = Mandate(
            **{
                **current.model_dump(),
                "revoked": True,
                "revoked_reason": "revoked while Muse was responding",
                "revision": str(int(current.revision) + 1),
            }
        )
        app_module.store.put("case-001", "mandate", revoked, app_module.now().isoformat())
        return ProposedActionCandidate(
            operation="package_export",
            allowed_device="device-A",
            destination="reviewer-authorized",
            reasoning="Prepare the verified evidence package.",
        )

    monkeypatch.setattr(app_module, "propose_action", revoke_during_call)
    response = client.post("/api/cases/case-001/actions/propose-with-muse", json={"principal": "investigator-A"})

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["verdict"] == "forbidden"
    assert body["prepared"] is None
    assert "revoked" in " ".join(body["decision"]["reasons"]).lower()


def test_propose_with_muse_surfaces_an_adapter_failure_as_502(client, monkeypatch):
    import krakadyl.api.app as app_module
    from krakadyl.adapters.muse import MuseAdapterError

    def failing_propose_action(**kwargs):
        raise MuseAdapterError("Muse response did not match the expected schema")

    monkeypatch.setattr(app_module, "propose_action", failing_propose_action)

    resp = client.post("/api/cases/case-001/actions/propose-with-muse", json={"principal": "investigator-A"})
    assert resp.status_code == 502


def test_state_survives_reloading_the_app_against_the_same_data_dir(tmp_path, monkeypatch):
    data_dir = str(tmp_path / "api")
    monkeypatch.setenv("KRAKADYL_DATA_DIR", data_dir)
    monkeypatch.setenv(
        "KRAKADYL_OPERATOR_TOKENS",
        f"investigator-A={hash_token('token-a')}",
    )

    import krakadyl.api.app as app_module

    importlib.reload(app_module)
    client1 = TestClient(app_module.app)
    client1.headers.update({"Authorization": "Bearer token-a"})
    prep = client1.post("/api/cases/case-001/actions/prepare", json={"principal": "investigator-A"}).json()
    assert prep["prepared"] is not None

    # Simulate a server restart: reload the module again against the
    # same KRAKADYL_DATA_DIR.
    importlib.reload(app_module)
    client2 = TestClient(app_module.app)
    client2.headers.update({"Authorization": "Bearer token-a"})
    fetched = client2.get(
        f"/api/cases/case-001/prepared/{prep['prepared']['id']}"
    ).json()
    assert fetched["prepared"]["id"] == prep["prepared"]["id"]
