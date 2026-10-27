"""Persistence: a case survives a reconnect (new KrakadylStore instance
against the same file), and nonce consumption survives it too — closing
the known gap tracked in docs/levels.md since Level 2 Cycle 1.
"""

from datetime import datetime, timedelta, timezone

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
