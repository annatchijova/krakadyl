"""SQLite-backed persistence for case state.

Closes two gaps at once: a case survives a server restart or page
reload (what the frontend needs — a session is not lost by refreshing
the tab), and nonce consumption (Level 2's replay protection) now
survives a process restart too, which `docs/levels.md` has tracked as a
known, deliberately-deferred gap since Cycle 1.

Every domain object is stored as its own canonical JSON via Pydantic's
`model_dump_json`/`model_validate_json` — this is NOT a parallel
schema. The stored bytes are exactly what the object's own Pydantic
model produces, read back through that same model, so there is only
ever one source of truth for what a Mission/Mandate/Observation/etc.
looks like. Appropriate for this level: a full relational schema with
joins is Level 4/6 concern (concurrent investigators, real query needs)
and would be premature here — this is accessed only through this
module's own API, so migrating later does not require touching callers.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    case_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    obj_id TEXT NOT NULL,
    json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (case_id, kind, obj_id)
);
CREATE TABLE IF NOT EXISTS nonces (
    nonce TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
"""


class KrakadylStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        journal_mode = self._conn.execute("PRAGMA journal_mode=WAL").fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "wal":
            self._conn.close()
            raise RuntimeError("SQLite refused to enable WAL journal mode")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

        # This lock serializes access to the shared connection on this
        # store instance. It does not make close() safe while callers
        # are still active.

    def close(self) -> None:
        """Close only after every caller has stopped using this store."""
        self._conn.close()

    # --- generic object storage, one row per domain object ---

    def put(self, case_id: str, kind: str, obj: BaseModel, now_iso: str) -> None:
        with self._write_lock, self._conn:
            self._conn.execute(
                "INSERT INTO objects (case_id, kind, obj_id, json, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(case_id, kind, obj_id) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at",
                (case_id, kind, obj.id, obj.model_dump_json(), now_iso),
            )

    def put_execution_receipt(self, case_id: str, obj: BaseModel, now_iso: str) -> None:
        payload = obj.model_dump_json()
        with self._write_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT json FROM objects WHERE case_id=? AND kind='receipt' AND obj_id=?",
                    (case_id, obj.id),
                ).fetchone()
                if row is None:
                    self._conn.execute(
                        "INSERT INTO objects (case_id, kind, obj_id, json, updated_at) "
                        "VALUES (?, 'receipt', ?, ?, ?)",
                        (case_id, obj.id, payload, now_iso),
                    )
                elif not json.loads(row[0]).get("executed") and getattr(obj, "executed", False):
                    self._conn.execute(
                        "UPDATE objects SET json=?, updated_at=? "
                        "WHERE case_id=? AND kind='receipt' AND obj_id=?",
                        (payload, now_iso, case_id, obj.id),
                    )
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise

    def get(self, case_id: str, kind: str, obj_id: str, model: Type[T]) -> Optional[T]:
        with self._write_lock:
            row = self._conn.execute(
                "SELECT json FROM objects WHERE case_id=? AND kind=? AND obj_id=?",
                (case_id, kind, obj_id),
            ).fetchone()
        return model.model_validate_json(row[0]) if row else None

    def list(self, case_id: str, kind: str, model: Type[T]) -> list[T]:
        # Tie-broken by rowid (SQLite's implicit insertion-order column),
        # not just updated_at — found by red-team review: two objects
        # written within the same ISO-timestamp tick would otherwise have
        # no defined order, and callers that read list(...)[-1] as "the
        # most recent" (api/app.py's get_case) would get an unstable
        # answer under that tie, not just a theoretical one.
        with self._write_lock:
            rows = self._conn.execute(
                "SELECT json FROM objects WHERE case_id=? AND kind=? ORDER BY updated_at, rowid",
                (case_id, kind),
            ).fetchall()
        return [model.model_validate_json(r[0]) for r in rows]

    def case_exists(self, case_id: str) -> bool:
        with self._write_lock:
            row = self._conn.execute("SELECT 1 FROM objects WHERE case_id=? LIMIT 1", (case_id,)).fetchone()
        return row is not None

    def reset_case(self, case_id: str) -> None:
        """Deletes every stored object and event for this case so it can
        be re-seeded from scratch — used only to replay the demo
        narrative repeatedly. Does not touch `nonces`: those are
        globally unique per `PreparedAction` already, so an orphaned
        nonce from a previous seeding cycle is simply never looked up
        again, not a correctness issue to clean up here.
        """
        with self._write_lock, self._conn:
            self._conn.execute("DELETE FROM objects WHERE case_id=?", (case_id,))
            self._conn.execute("DELETE FROM events WHERE case_id=?", (case_id,))

    # --- nonces: global, not per-case — a PreparedAction's nonce is
    # already globally unique (secrets.token_hex(8)) ---

    def consume_nonce(self, nonce: str) -> bool:
        """True if this nonce was not already consumed (and is now
        recorded); False if it was already used — the caller must treat
        False as a replay, never retry silently.
        """
        try:
            with self._write_lock, self._conn:
                self._conn.execute("INSERT INTO nonces (nonce) VALUES (?)", (nonce,))
            return True
        except sqlite3.IntegrityError:
            return False

    def claim_nonce(self, case_id: str, nonce: str, prepared_action_id: str, now_iso: str) -> bool:
        try:
            with self._write_lock, self._conn:
                self._conn.execute("INSERT INTO nonces (nonce) VALUES (?)", (nonce,))
                self._conn.execute(
                    "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        case_id,
                        now_iso,
                        "execution_claimed",
                        "Claimed a one-time execution attempt",
                        json.dumps({"prepared_action_id": prepared_action_id}),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def consumed_nonces(self) -> set[str]:
        with self._write_lock:
            rows = self._conn.execute("SELECT nonce FROM nonces").fetchall()
        return {r[0] for r in rows}

    # --- activity feed ---

    def log_event(self, case_id: str, kind: str, summary: str, detail: dict, now_iso: str) -> None:
        with self._write_lock, self._conn:
            self._conn.execute(
                "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
                (case_id, now_iso, kind, summary, json.dumps(detail)),
            )

    def list_events(self, case_id: str) -> list[dict]:
        with self._write_lock:
            rows = self._conn.execute(
                "SELECT ts, kind, summary, detail_json FROM events WHERE case_id=? ORDER BY id",
                (case_id,),
            ).fetchall()
        return [
            {"ts": ts, "kind": kind, "summary": summary, "detail": json.loads(detail_json)}
            for ts, kind, summary, detail_json in rows
        ]
