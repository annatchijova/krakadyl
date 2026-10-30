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
from typing import Callable, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")

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
CREATE TABLE IF NOT EXISTS acquisition_schema_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS acquisition_gate_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    dispatch_generation INTEGER NOT NULL CHECK (dispatch_generation >= 0)
);
CREATE TABLE IF NOT EXISTS acquisition_workflows (
    workflow_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    authorization_id TEXT NOT NULL UNIQUE,
    proposal_json TEXT NOT NULL,
    authorization_json TEXT,
    mandate_digest TEXT,
    workflow_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active', 'unknown', 'completed', 'failed')),
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS acquisition_active_requirement
ON acquisition_workflows (case_id, requirement_id)
WHERE state IN ('active', 'unknown');
CREATE TABLE IF NOT EXISTS acquisition_attempts (
    attempt_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES acquisition_workflows(workflow_id),
    case_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    state TEXT NOT NULL,
    request_reference TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    attempt_json TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (workflow_id, phase)
);
CREATE TABLE IF NOT EXISTS acquisition_requests (
    attempt_id TEXT PRIMARY KEY REFERENCES acquisition_attempts(attempt_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    request_json TEXT NOT NULL,
    retention_json TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS acquisition_reservations (
    workflow_id TEXT NOT NULL REFERENCES acquisition_workflows(workflow_id),
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    reserved_json TEXT NOT NULL,
    committed_json TEXT NOT NULL,
    PRIMARY KEY (workflow_id, scope_type, scope_id)
);
CREATE TABLE IF NOT EXISTS acquisition_revocations (
    authorization_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    revocation_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS acquisition_resolutions (
    resolution_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES acquisition_attempts(attempt_id),
    case_id TEXT NOT NULL,
    resolution_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (attempt_id)
);
CREATE TABLE IF NOT EXISTS acquisition_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL REFERENCES acquisition_workflows(workflow_id),
    requirement_id TEXT NOT NULL,
    evaluator_identity TEXT NOT NULL,
    evaluation_json TEXT NOT NULL,
    evaluation_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workflow_id, evaluator_identity)
);
CREATE TABLE IF NOT EXISTS team_records (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    record_json TEXT NOT NULL,
    record_digest TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- Level 4: a teammate's statement is never rewritten; a correction is a
-- new record. Deletion stays possible only for the token-gated dev reset.
CREATE TRIGGER IF NOT EXISTS team_records_append_only
BEFORE UPDATE ON team_records
BEGIN
    SELECT RAISE(ABORT, 'team records are append-only');
END;
CREATE TABLE IF NOT EXISTS shift_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS shift_events_append_only
BEFORE UPDATE ON shift_events
BEGIN
    SELECT RAISE(ABORT, 'shift events are append-only');
END;
CREATE TABLE IF NOT EXISTS counterfactuals (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    counterfactual_id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    counterfactual_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- Level 5: hypotheticals live here and only here — never in `objects`,
-- which is what every real decision reads.
CREATE TRIGGER IF NOT EXISTS counterfactuals_append_only
BEFORE UPDATE ON counterfactuals
BEGIN
    SELECT RAISE(ABORT, 'counterfactuals are append-only');
END;
CREATE TABLE IF NOT EXISTS acquisition_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
"""


class KrakadylStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        journal_mode = self._conn.execute("PRAGMA journal_mode=WAL").fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "wal":
            self._conn.close()
            raise RuntimeError("SQLite refused to enable WAL journal mode")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO acquisition_schema_meta (singleton, version) VALUES (1, 1)"
            )
            schema_version = self._conn.execute(
                "SELECT version FROM acquisition_schema_meta WHERE singleton=1"
            ).fetchone()
            if schema_version is None or schema_version[0] not in (1, 2, 3, 4, 5, 6, 7):
                raise RuntimeError("unsupported SQLite acquisition schema version")
            if schema_version[0] < 3:
                workflow_columns = {
                    row[1] for row in self._conn.execute("PRAGMA table_info(acquisition_workflows)")
                }
                attempt_columns = {
                    row[1] for row in self._conn.execute("PRAGMA table_info(acquisition_attempts)")
                }
                if "authorization_json" not in workflow_columns:
                    self._conn.execute(
                        "ALTER TABLE acquisition_workflows ADD COLUMN authorization_json TEXT"
                    )
                if "mandate_digest" not in workflow_columns:
                    self._conn.execute(
                        "ALTER TABLE acquisition_workflows ADD COLUMN mandate_digest TEXT"
                    )
                if "result_json" not in attempt_columns:
                    self._conn.execute("ALTER TABLE acquisition_attempts ADD COLUMN result_json TEXT")
                self._conn.execute(
                    "UPDATE acquisition_schema_meta SET version=3 WHERE singleton=1"
                )
            self._conn.execute(
                "INSERT OR IGNORE INTO acquisition_gate_state (singleton, dispatch_generation) VALUES (1, 0)"
            )
            if schema_version[0] < 7:
                # v5 added acquisition_evaluations, v6 team_records and
                # shift_events, v7 counterfactuals (the last three with
                # append-only triggers), all created above by
                # CREATE ... IF NOT EXISTS; no existing row changes.
                self._conn.execute(
                    "UPDATE acquisition_schema_meta SET version=7 WHERE singleton=1"
                )
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            self._conn.close()
            raise

        # This lock serializes access to the shared connection on this
        # store instance. It does not make close() safe while callers
        # are still active.

    def close(self) -> None:
        """Close only after every caller has stopped using this store."""
        self._conn.close()

    def atomic_write(self, operation: Callable[[sqlite3.Connection], R]) -> R:
        """Run one database-wide state transition under the shared write lock."""
        with self._write_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                result = operation(self._conn)
                self._conn.commit()
                return result
            except BaseException:
                self._conn.rollback()
                raise

    def read_locked(self, operation: Callable[[sqlite3.Connection], R]) -> R:
        """Serialize a bounded read callback against users of the shared connection."""
        with self._write_lock:
            return operation(self._conn)

    # --- generic object storage, one row per domain object ---

    def put(self, case_id: str, kind: str, obj: BaseModel, now_iso: str) -> None:
        with self._write_lock, self._conn:
            self._conn.execute(
                "INSERT INTO objects (case_id, kind, obj_id, json, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(case_id, kind, obj_id) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at",
                (case_id, kind, obj.id, obj.model_dump_json(), now_iso),
            )

    @staticmethod
    def _put_object(connection: sqlite3.Connection, case_id: str, kind: str, obj: BaseModel, now_iso: str) -> None:
        connection.execute(
            "INSERT INTO objects (case_id, kind, obj_id, json, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(case_id, kind, obj_id) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at",
            (case_id, kind, obj.id, obj.model_dump_json(), now_iso),
        )

    def put_prepare_result(
        self,
        case_id: str,
        proposed_action: BaseModel,
        decision: BaseModel,
        prepared: Optional[BaseModel],
        now_iso: str,
    ) -> None:
        """Persist the complete prepare result as one logical transition."""
        def transition(connection: sqlite3.Connection) -> None:
            self._put_object(connection, case_id, "proposed_action", proposed_action, now_iso)
            self._put_object(connection, case_id, "decision", decision, now_iso)
            if prepared is not None:
                self._put_object(connection, case_id, "prepared_action", prepared, now_iso)

        self.atomic_write(transition)

    def put_prepare_result_and_log_event(
        self,
        case_id: str,
        proposed_action: BaseModel,
        decision: BaseModel,
        prepared: Optional[BaseModel],
        event_kind: str,
        summary: str,
        detail: dict,
        now_iso: str,
    ) -> None:
        """Persist a prepared result and its activity event atomically."""
        def transition(connection: sqlite3.Connection) -> None:
            self._put_object(connection, case_id, "proposed_action", proposed_action, now_iso)
            self._put_object(connection, case_id, "decision", decision, now_iso)
            if prepared is not None:
                self._put_object(connection, case_id, "prepared_action", prepared, now_iso)
            connection.execute(
                "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
                (case_id, now_iso, event_kind, summary, json.dumps(detail)),
            )

        self.atomic_write(transition)

    def put_and_log_event(
        self,
        case_id: str,
        kind: str,
        obj: BaseModel,
        event_kind: str,
        summary: str,
        detail: dict,
        now_iso: str,
    ) -> None:
        """Persist an object and its reconstruction event atomically."""
        def transition(connection: sqlite3.Connection) -> None:
            self._put_object(connection, case_id, kind, obj, now_iso)
            connection.execute(
                "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
                (case_id, now_iso, event_kind, summary, json.dumps(detail)),
            )

        self.atomic_write(transition)

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
            # Acquisition records too, children before parents (foreign
            # keys are enforced). Only the dev reset reaches this; a real
            # case never deletes its acquisition audit trail.
            workflow_ids = "SELECT workflow_id FROM acquisition_workflows WHERE case_id=?"
            attempt_ids = f"SELECT attempt_id FROM acquisition_attempts WHERE workflow_id IN ({workflow_ids})"
            self._conn.execute(f"DELETE FROM acquisition_evaluations WHERE workflow_id IN ({workflow_ids})", (case_id,))
            self._conn.execute(f"DELETE FROM acquisition_resolutions WHERE attempt_id IN ({attempt_ids})", (case_id,))
            self._conn.execute(f"DELETE FROM acquisition_requests WHERE attempt_id IN ({attempt_ids})", (case_id,))
            self._conn.execute(f"DELETE FROM acquisition_attempts WHERE workflow_id IN ({workflow_ids})", (case_id,))
            self._conn.execute(f"DELETE FROM acquisition_reservations WHERE workflow_id IN ({workflow_ids})", (case_id,))
            self._conn.execute("DELETE FROM acquisition_events WHERE case_id=?", (case_id,))
            self._conn.execute("DELETE FROM team_records WHERE case_id=?", (case_id,))
            self._conn.execute("DELETE FROM shift_events WHERE case_id=?", (case_id,))
            self._conn.execute("DELETE FROM counterfactuals WHERE case_id=?", (case_id,))
            self._conn.execute("DELETE FROM acquisition_revocations WHERE case_id=?", (case_id,))
            self._conn.execute("DELETE FROM acquisition_workflows WHERE case_id=?", (case_id,))

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
