"""Persistence: a case survives a reconnect (new KrakadylStore instance
against the same file), and nonce consumption survives it too — closing
the known gap tracked in docs/levels.md since Level 2 Cycle 1.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from queue import Queue
from threading import Barrier, Thread

from krakadyl.core.models import Mandate
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
