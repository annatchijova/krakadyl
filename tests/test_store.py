"""Persistence: a case survives a reconnect (new KrakadylStore instance
against the same file), and nonce consumption survives it too — closing
the known gap tracked in docs/levels.md since Level 2 Cycle 1.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from queue import Queue
from threading import Barrier, Thread

import pytest

from krakadyl.core.models import Mandate, Receipt
from krakadyl.store import KrakadylStore

NOW = datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc)


def _mandate(**overrides) -> Mandate:
    defaults = dict(
        id="mandate-001",
        issuer="legal-authority-001",
        principal="investigator-A",
        resources=["case-001/device-A"],
        operations=["package_export"],
        destinations=["reviewer-authorized"],
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=5),
    )
    defaults.update(overrides)
    return Mandate(**defaults)


def test_put_and_get_round_trips_through_the_real_pydantic_model(tmp_path):
    store = KrakadylStore(tmp_path / "krakadyl.db")
    store.put("case-001", "mandate", _mandate(), NOW.isoformat())

    fetched = store.get("case-001", "mandate", "mandate-001", Mandate)
    assert fetched is not None
    assert fetched.revision == "1"
    assert fetched.resources == ["case-001/device-A"]


def test_state_survives_a_new_store_instance_against_the_same_file(tmp_path):
    db_path = tmp_path / "krakadyl.db"
    store1 = KrakadylStore(db_path)
    store1.put("case-001", "mandate", _mandate(), NOW.isoformat())
    store1.close()

    store2 = KrakadylStore(db_path)
    fetched = store2.get("case-001", "mandate", "mandate-001", Mandate)
    assert fetched is not None
    assert fetched.id == "mandate-001"


def test_put_overwrites_the_same_object_id(tmp_path):
    store = KrakadylStore(tmp_path / "krakadyl.db")
    store.put("case-001", "mandate", _mandate(revision="1"), NOW.isoformat())
    store.put("case-001", "mandate", _mandate(revision="2", revoked=True), NOW.isoformat())

    fetched = store.get("case-001", "mandate", "mandate-001", Mandate)
    assert fetched.revision == "2"
    assert fetched.revoked is True


def test_nonce_consumption_is_one_time_only(tmp_path):
    store = KrakadylStore(tmp_path / "krakadyl.db")
    assert store.consume_nonce("abc123") is True
    assert store.consume_nonce("abc123") is False
    assert "abc123" in store.consumed_nonces()


def test_nonce_consumption_survives_a_new_store_instance(tmp_path):
    db_path = tmp_path / "krakadyl.db"
    store1 = KrakadylStore(db_path)
    store1.consume_nonce("abc123")
    store1.close()

    store2 = KrakadylStore(db_path)
    assert store2.consume_nonce("abc123") is False


def test_concurrent_nonce_claims_across_store_instances_have_one_winner(tmp_path):
    db_path = tmp_path / "krakadyl.db"
    stores = [KrakadylStore(db_path), KrakadylStore(db_path)]
    barrier = Barrier(2)
    results = Queue()

    def claim(store):
        barrier.wait(timeout=2)
        results.put(store.claim_nonce("case-001", "shared-nonce", "prepared-1", NOW.isoformat()))

    threads = [Thread(target=claim, args=(store,)) for store in stores]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(results.get_nowait() for _ in range(2)) == [False, True]
    assert [event["kind"] for event in stores[0].list_events("case-001")] == ["execution_claimed"]


def test_successful_receipt_wins_concurrent_persistence_across_store_instances(tmp_path):
    db_path = tmp_path / "krakadyl.db"
    stores = [KrakadylStore(db_path), KrakadylStore(db_path)]
    barrier = Barrier(2)
    failures = Queue()
    denied = Receipt(
        id="receipt-action-1",
        proposed_action_id="action-1",
        decision_id="decision-1",
        executed=False,
        observed_effect="replay denied",
        hash="denied-hash",
        created_at=NOW,
    )
    successful = denied.model_copy(update={"executed": True, "observed_effect": "package published", "hash": "success-hash"})

    def persist(store, receipt):
        try:
            barrier.wait(timeout=2)
            store.put_execution_receipt("case-001", receipt, NOW.isoformat())
        except BaseException as exc:
            failures.put(exc)

    threads = [
        Thread(target=persist, args=(stores[0], denied)),
        Thread(target=persist, args=(stores[1], successful)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert failures.empty()
    persisted = stores[0].get("case-001", "receipt", denied.id, Receipt)
    assert persisted.executed is True
    assert persisted.hash == "success-hash"


def test_list_breaks_ties_by_insertion_order_not_just_timestamp(tmp_path):
    """Found by red-team review: ORDER BY updated_at alone has no
    defined tiebreak for two objects written with the identical
    timestamp string — a real, if narrow, risk for callers like
    api/app.py's get_case(), which reads list(...)[-1] as "the most
    recently created." rowid (SQLite's implicit insertion-order column)
    makes that order well-defined instead of accidental.
    """
    store = KrakadylStore(tmp_path / "krakadyl.db")
    same_ts = NOW.isoformat()
    store.put("case-001", "mandate", _mandate(id="mandate-A", revision="1"), same_ts)
    store.put("case-001", "mandate", _mandate(id="mandate-B", revision="1"), same_ts)
    store.put("case-001", "mandate", _mandate(id="mandate-C", revision="1"), same_ts)

    ordered = store.list("case-001", "mandate", Mandate)
    assert [m.id for m in ordered] == ["mandate-A", "mandate-B", "mandate-C"]


def test_events_are_recorded_in_order(tmp_path):
    store = KrakadylStore(tmp_path / "krakadyl.db")
    store.log_event("case-001", "prepared", "Action prepared", {"id": "prep-1"}, NOW.isoformat())
    store.log_event("case-001", "executed", "Action executed", {"id": "prep-1"}, NOW.isoformat())

    events = store.list_events("case-001")
    assert [e["kind"] for e in events] == ["prepared", "executed"]


def test_duplicate_nonce_rolls_back_before_returning_false(tmp_path):
    db_path = tmp_path / "krakadyl.db"
    first = KrakadylStore(db_path)
    second = KrakadylStore(db_path)

    assert first.consume_nonce("duplicate") is True
    assert first.consume_nonce("duplicate") is False
    assert first._conn.in_transaction is False
    assert second.consume_nonce("other-writer") is True


def test_store_enables_wal_on_the_database_file(tmp_path):
    db_path = tmp_path / "krakadyl.db"
    KrakadylStore(db_path)

    with sqlite3.connect(db_path) as observer:
        mode = observer.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode == "wal"


def test_every_write_transaction_holds_the_instance_write_lock(tmp_path):
    store = KrakadylStore(tmp_path / "krakadyl.db")
    assert hasattr(store, "_write_lock")
    traced = []
    store._conn.set_trace_callback(
        lambda statement: traced.append((statement, store._write_lock.locked()))
    )

    store.put(
        "case-001",
        "mandate",
        _mandate(id="mandate-traced"),
        NOW.isoformat(),
    )
    assert store.consume_nonce("traced-nonce") is True
    assert store.consume_nonce("traced-nonce") is False
    store.log_event(
        "case-001",
        "traced",
        "Trace the write lock",
        {"id": "trace-1"},
        NOW.isoformat(),
    )
    store.reset_case("case-001")

    transaction_statements = [
        (statement, locked)
        for statement, locked in traced
        if statement.lstrip().upper().startswith(
            ("BEGIN", "INSERT", "UPDATE", "DELETE", "COMMIT", "ROLLBACK")
        )
    ]
    assert transaction_statements
    assert all(locked for _, locked in transaction_statements)
    assert any(
        statement.lstrip().upper().startswith("ROLLBACK")
        for statement, _ in transaction_statements
    )


def test_two_threads_can_write_fifty_distinct_objects_without_loss(tmp_path):
    store = KrakadylStore(tmp_path / "krakadyl.db")
    barrier = Barrier(2)
    failures = Queue()

    def write_mandates(prefix: str) -> None:
        try:
            for index in range(25):
                barrier.wait(timeout=2)
                store.put(
                    "case-001",
                    "mandate",
                    _mandate(id=f"mandate-{prefix}-{index}"),
                    NOW.isoformat(),
                )
        except BaseException as exc:
            failures.put(exc)

    threads = [
        Thread(target=write_mandates, args=("a",)),
        Thread(target=write_mandates, args=("b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    caught = []
    while not failures.empty():
        caught.append(failures.get_nowait())
    assert caught == []

    stored_ids = {
        mandate.id for mandate in store.list("case-001", "mandate", Mandate)
    }
    expected_ids = {
        f"mandate-{prefix}-{index}"
        for prefix in ("a", "b")
        for index in range(25)
    }
    assert stored_ids == expected_ids


def test_atomic_write_rolls_back_all_callback_mutations(tmp_path):
    store = KrakadylStore(tmp_path / "krakadyl.db")

    def fail_after_insert(connection):
        connection.execute(
            "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
            ("case-001", NOW.isoformat(), "partial", "must roll back", "{}"),
        )
        raise RuntimeError("injected transaction failure")

    with pytest.raises(RuntimeError, match="injected transaction failure"):
        store.atomic_write(fail_after_insert)

    assert store.list_events("case-001") == []
    assert store._conn.in_transaction is False


def test_prepare_result_rolls_back_its_bundle_on_failure(tmp_path):
    store = KrakadylStore(tmp_path / "krakadyl.db")
    store.atomic_write(lambda connection: connection.execute(
        "CREATE TRIGGER fail_decision_insert BEFORE INSERT ON objects "
        "WHEN NEW.kind='decision' BEGIN SELECT RAISE(ABORT, 'decision rejected'); END"
    ))

    with pytest.raises(sqlite3.IntegrityError, match="decision rejected"):
        store.put_prepare_result(
            "case-001", _mandate(id="proposal-1"), _mandate(id="decision-1"),
            _mandate(id="prepared-1"), NOW.isoformat(),
        )

    rows = store.read_locked(lambda connection: connection.execute(
        "SELECT kind FROM objects WHERE case_id=? ORDER BY kind", ("case-001",)
    ).fetchall())
    assert rows == []


def test_object_and_audit_event_roll_back_together(tmp_path):
    store = KrakadylStore(tmp_path / "krakadyl.db")
    store.atomic_write(lambda connection: connection.execute(
        "CREATE TRIGGER fail_audit_event BEFORE INSERT ON events "
        "WHEN NEW.kind='proposal' BEGIN SELECT RAISE(ABORT, 'audit rejected'); END"
    ))

    with pytest.raises(sqlite3.IntegrityError, match="audit rejected"):
        store.put_and_log_event(
            "case-001", "acquisition_proposal", _mandate(id="proposal-1"),
            "proposal", "proposal created", {}, NOW.isoformat(),
        )

    assert store.read_locked(lambda connection: connection.execute(
        "SELECT COUNT(*) FROM objects WHERE case_id=?", ("case-001",)
    ).fetchone()[0]) == 0
    assert store.list_events("case-001") == []


def test_acquisition_schema_v1_migrates_additively_to_v7(tmp_path):
    database = tmp_path / "legacy-acquisition.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        "CREATE TABLE acquisition_schema_meta (singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL);"
        "INSERT INTO acquisition_schema_meta VALUES (1, 1);"
        "CREATE TABLE acquisition_workflows ("
        "workflow_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, requirement_id TEXT NOT NULL, "
        "authorization_id TEXT NOT NULL UNIQUE, proposal_json TEXT NOT NULL, "
        "workflow_json TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);"
        "CREATE TABLE acquisition_attempts ("
        "attempt_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, case_id TEXT NOT NULL, "
        "phase TEXT NOT NULL, state TEXT NOT NULL, request_reference TEXT NOT NULL, "
        "request_digest TEXT NOT NULL, attempt_json TEXT NOT NULL, created_at TEXT NOT NULL, "
        "UNIQUE (workflow_id, phase));"
        "INSERT INTO acquisition_workflows VALUES "
        "('workflow-v1', 'case-v1', 'requirement-v1', 'authorization-v1', '{}', '{}', 'active', '2026-10-27T16:00:00+00:00');"
        "INSERT INTO acquisition_attempts VALUES "
        "('attempt-v1', 'workflow-v1', 'case-v1', 'source_capture', 'dispatch_intent', 'ref', 'digest', '{}', '2026-10-27T16:00:00+00:00');"
    )
    connection.close()

    store = KrakadylStore(database)

    columns = store.read_locked(lambda conn: (
        {row[1] for row in conn.execute("PRAGMA table_info(acquisition_workflows)")},
        {row[1] for row in conn.execute("PRAGMA table_info(acquisition_attempts)")},
        conn.execute("SELECT version FROM acquisition_schema_meta WHERE singleton=1").fetchone()[0],
        conn.execute("SELECT dispatch_generation FROM acquisition_gate_state WHERE singleton=1").fetchone()[0],
        conn.execute("SELECT workflow_id, mandate_digest FROM acquisition_workflows").fetchone(),
        conn.execute("SELECT attempt_id FROM acquisition_attempts").fetchone()[0],
        {row[1] for row in conn.execute("PRAGMA table_info(acquisition_evaluations)")},
    ))
    assert "authorization_json" in columns[0]
    assert "mandate_digest" in columns[0]
    assert "result_json" in columns[1]
    assert columns[2] == 7
    assert columns[3] == 0
    assert columns[4] == ("workflow-v1", None)
    assert columns[5] == "attempt-v1"
    assert {"evaluation_id", "workflow_id", "evaluator_identity", "evaluation_json"} <= columns[6]
    store.close()


def test_receipt_head_follows_append_order_not_handler_timestamp(tmp_path):
    """Red-team RT-CHAIN-01 (live concurrency fork): append_execution_receipt
    picked the chain head by updated_at, which is a handler-side timestamp
    computed before the write lock is won. A later-appended receipt carrying an
    earlier timestamp was therefore invisible as the head, so the next append
    linked to a stale predecessor and the chain forked. The head must follow
    append order (rowid), not the timestamp.
    """
    from krakadyl.core.receipt import seal

    store = KrakadylStore(tmp_path / "krakadyl.db")

    def relink(receipt, prev_hash):
        return receipt.model_copy(update={"prev_hash": prev_hash, "hash": seal(receipt.seal_payload, prev_hash)})

    def receipt(obj_id, payload):
        # prev_hash is a sentinel so append always relinks against the real
        # head (never equal to it), giving every receipt a genuine sealed hash.
        return Receipt(
            id=obj_id, proposed_action_id=obj_id, decision_id=f"d-{obj_id}",
            executed=True, observed_effect="ok", hash="x" * 64, prev_hash="__force_relink__",
            created_at=NOW, seal_payload=payload,
        )

    # r1 appended first, with a LATER timestamp.
    r1 = store.append_execution_receipt(
        "case-001", receipt("receipt-1", {"n": 1}), "2026-10-31T00:00:05+00:00", relink)
    # r2 appended second, with an EARLIER timestamp than r1 (the inversion the
    # live race produces). It correctly links to r1.
    r2 = store.append_execution_receipt(
        "case-001", receipt("receipt-2", {"n": 2}), "2026-10-31T00:00:01+00:00", relink)
    assert r2.prev_hash == r1.hash

    # r3 must link to r2 (the actually-last-appended receipt), not back to r1
    # just because r1 has the larger timestamp. Linking to r1 is the fork.
    r3 = store.append_execution_receipt(
        "case-001", receipt("receipt-3", {"n": 3}), "2026-10-31T00:00:03+00:00", relink)
    assert r3.prev_hash == r2.hash, "chain forked: r3 linked to a stale predecessor by timestamp"
    assert r3.prev_hash != r1.hash


def test_replacing_a_denied_receipt_links_to_the_real_head_not_itself(tmp_path):
    """Red-team RT-CHAIN-02 (replay-race dangling link): when a denied receipt
    for an action is persisted before the successful one (same obj_id), the
    successful replacement must link to the real chain head, never to the
    denied receipt's own transient hash in the row being overwritten.
    """
    from krakadyl.core.receipt import seal

    store = KrakadylStore(tmp_path / "krakadyl.db")

    def relink(receipt, prev_hash):
        return receipt.model_copy(update={"prev_hash": prev_hash, "hash": seal(receipt.seal_payload, prev_hash)})

    def rc(obj_id, payload, executed):
        return Receipt(
            id=obj_id, proposed_action_id=obj_id, decision_id=f"d-{obj_id}",
            executed=executed, observed_effect="x", hash="x" * 64, prev_hash="__force_relink__",
            created_at=NOW, seal_payload=payload,
        )

    head = store.append_execution_receipt(
        "case-x", rc("r-prev", {"n": 0}, True), "2026-10-31T00:00:00+00:00", relink)
    # A denied receipt for action R appends first, linking to the real head.
    denied = store.append_execution_receipt(
        "case-x", rc("r-R", {"n": 1, "denied": True}, False), "2026-10-31T00:00:01+00:00", relink)
    assert denied.prev_hash == head.hash
    # The successful receipt for the SAME action R replaces it; it must link to
    # the real head, not to the denied row it is about to overwrite.
    winner = store.append_execution_receipt(
        "case-x", rc("r-R", {"n": 1, "won": True}, True), "2026-10-31T00:00:02+00:00", relink)
    assert winner.prev_hash == head.hash, "successful replacement linked to a stale/self predecessor"
    stored = store.get("case-x", "receipt", "r-R", Receipt)
    assert stored.executed is True and stored.prev_hash == head.hash
