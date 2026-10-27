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
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- generic object storage, one row per domain object ---

    def put(self, case_id: str, kind: str, obj: BaseModel, now_iso: str) -> None:
        self._conn.execute(
            "INSERT INTO objects (case_id, kind, obj_id, json, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(case_id, kind, obj_id) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at",
            (case_id, kind, obj.id, obj.model_dump_json(), now_iso),
        )
        self._conn.commit()

    def get(self, case_id: str, kind: str, obj_id: str, model: Type[T]) -> Optional[T]:
        row = self._conn.execute(
            "SELECT json FROM objects WHERE case_id=? AND kind=? AND obj_id=?",
            (case_id, kind, obj_id),
        ).fetchone()
        return model.model_validate_json(row[0]) if row else None

    def list(self, case_id: str, kind: str, model: Type[T]) -> list[T]:
        rows = self._conn.execute(
            "SELECT json FROM objects WHERE case_id=? AND kind=? ORDER BY updated_at",
            (case_id, kind),
        ).fetchall()
        return [model.model_validate_json(r[0]) for r in rows]

    def case_exists(self, case_id: str) -> bool:
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
        self._conn.execute("DELETE FROM objects WHERE case_id=?", (case_id,))
        self._conn.execute("DELETE FROM events WHERE case_id=?", (case_id,))
        self._conn.commit()

    # --- nonces: global, not per-case — a PreparedAction's nonce is
    # already globally unique (secrets.token_hex(8)) ---

    def consume_nonce(self, nonce: str) -> bool:
        """True if this nonce was not already consumed (and is now
        recorded); False if it was already used — the caller must treat
        False as a replay, never retry silently.
        """
        try:
            self._conn.execute("INSERT INTO nonces (nonce) VALUES (?)", (nonce,))
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def consumed_nonces(self) -> set[str]:
        rows = self._conn.execute("SELECT nonce FROM nonces").fetchall()
        return {r[0] for r in rows}

    # --- activity feed ---

    def log_event(self, case_id: str, kind: str, summary: str, detail: dict, now_iso: str) -> None:
        self._conn.execute(
            "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
            (case_id, now_iso, kind, summary, json.dumps(detail)),
        )
        self._conn.commit()

    def list_events(self, case_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, kind, summary, detail_json FROM events WHERE case_id=? ORDER BY id",
            (case_id,),
        ).fetchall()
        return [
            {"ts": ts, "kind": kind, "summary": summary, "detail": json.loads(detail_json)}
            for ts, kind, summary, detail_json in rows
        ]
