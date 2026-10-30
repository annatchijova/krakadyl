"""Shift handoff: "what do I need to know to pick this up", from recorded state.

`build_shift_handoff` is a pure read: it composes what the case already
records — requirements, team records, conflicts, acquisitions in flight,
hypotheses needing review, the next move — into one view, ordered so the
loudest things come first (open conflicts, then claims about to lose
their window). It never re-decides anything those modules decided.

Its `state_digest` covers everything in the view except the generation
time, so a handoff can be bound to exactly what the outgoing person saw,
and the incoming person learns whether the case moved since.

Handing off work is not handing off authority: an accepted handoff can
make the incoming person the *owner* of requirements, but never touches
any mandate. Who may capture or package is decided by mandates alone.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from krakadyl.core.acquisition import requirement_revision_digest
from krakadyl.core.continuity import NextMove, find_urgent_discrepancies, next_move
from krakadyl.core.invalidation import find_hypotheses_needing_review
from krakadyl.core.models import EvidenceRequirement, Hypothesis, Observation, TaskResponsibility, TaskStatus
from krakadyl.core.receipt import canonical_bytes
from krakadyl.core.team import Conflict, RefChecker, TeamRecord, find_conflicts
from krakadyl.store import KrakadylStore


class HandoffItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    requirement_id: str
    summary: str
    owner: str
    provenance: tuple[str, ...] = ()
    minutes_left: Optional[float] = None


class InFlightAcquisition(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow_id: str
    requirement_id: str
    state: str


class ShiftHandoff(BaseModel):
    case_id: str
    generated_at: datetime
    state_digest: str
    open_conflicts: list[Conflict]
    urgent_unverified: list[HandoffItem]
    claimed_unverified: list[HandoffItem]
    not_acknowledged: list[HandoffItem]
    blocked: list[HandoffItem]
    uncertain_status: list[HandoffItem]
    acquisitions_in_flight: list[InFlightAcquisition]
    hypotheses_needing_review: list[tuple[str, str]]
    verified: list[HandoffItem]
    closed_unresolvable: list[HandoffItem]
    next_move: NextMove


def _records_for(records: list[TeamRecord], requirement_id: str, kinds) -> tuple[str, ...]:
    return tuple(r.record_id for r in records if r.requirement_id == requirement_id and r.kind.value in kinds)


def build_shift_handoff(
    *,
    case_id: str,
    requirements: list[EvidenceRequirement],
    hypotheses: list[Hypothesis],
    records: list[TeamRecord],
    check_ref: RefChecker,
    acquisitions: list[InFlightAcquisition],
    now: datetime,
    observations: Optional[list[Observation]] = None,
    observation_files: Optional[dict[str, Path]] = None,
) -> ShiftHandoff:
    conflicts: list[Conflict] = []
    for r in requirements:
        conflicts.extend(find_conflicts(r.id, records, check_ref)[0])
    urgent = {d.requirement_id: d for d in find_urgent_discrepancies(requirements, now)}

    def item(r: EvidenceRequirement, summary: str, kinds=(), minutes_left=None) -> HandoffItem:
        return HandoffItem(requirement_id=r.id, summary=summary, owner=r.responsibility.owner,
                           provenance=_records_for(records, r.id, kinds), minutes_left=minutes_left)

    sections: dict[str, list[HandoffItem]] = {
        k: [] for k in ("urgent", "claimed", "not_ack", "blocked", "uncertain", "verified", "closed")
    }
    for r in sorted(requirements, key=lambda x: x.id):
        status = r.responsibility.status
        if r.unresolvable:
            sections["closed"].append(item(r, f"closed as unresolvable: {r.unresolvable_reason}"))
        elif r.resolved and status == TaskStatus.VERIFIED_DONE:
            sections["verified"].append(item(
                r, f"verified by {r.responsibility.verified_by} ({r.responsibility.verification_method})",
                {"verified", "reported_done"}))
        elif r.id in urgent:
            sections["urgent"].append(item(r, urgent[r.id].reason, {"reported_done"}, urgent[r.id].minutes_left))
        elif status == TaskStatus.REPORTED_DONE:
            sections["claimed"].append(item(
                r, f"reported done by {r.responsibility.reported_done_by}; no independent verification recorded",
                {"reported_done"}))
        elif status == TaskStatus.ASSIGNED:
            sections["not_ack"].append(item(r, "assigned; the owner has not acknowledged it yet"))
        elif status == TaskStatus.BLOCKED:
            sections["blocked"].append(item(
                r, r.blocked_reason or "reported blocked by its owner", {"blocked"}))
        elif status == TaskStatus.UNKNOWN:
            sections["uncertain"].append(item(
                r, "whether this was done is unknown (reopened after a resolved conflict, or never reported)",
                {"resolution", "disputed"}))

    body = {
        "case_id": case_id,
        "open_conflicts": conflicts,
        "urgent_unverified": sections["urgent"],
        "claimed_unverified": sections["claimed"],
        "not_acknowledged": sections["not_ack"],
        "blocked": sections["blocked"],
        "uncertain_status": sections["uncertain"],
        "acquisitions_in_flight": [a for a in acquisitions if a.state in ("active", "unknown")],
        "hypotheses_needing_review": find_hypotheses_needing_review(
            hypotheses,
            requirements,
            observations=observations,
            observation_files=observation_files,
        ),
        "verified": sections["verified"],
        "closed_unresolvable": sections["closed"],
        "next_move": next_move(requirements),
    }
    probe = ShiftHandoff(generated_at=now, state_digest="0" * 64, **body)
    payload = probe.model_dump(mode="json", exclude={"generated_at", "state_digest"})
    digest = hashlib.sha256(canonical_bytes(_floats_to_text(payload))).hexdigest()
    return probe.model_copy(update={"state_digest": digest})


def _floats_to_text(value):
    """`minutes_left` is a float for display; the digest encoder refuses
    floats on purpose, so they are hashed as fixed-precision text."""
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, dict):
        return {k: _floats_to_text(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_floats_to_text(v) for v in value]
    return value


def handoff_text_lines(handoff: ShiftHandoff) -> list[str]:
    """Every generated sentence in the view, for the no-blame language check."""
    lines = [c.description for c in handoff.open_conflicts]
    for section in (handoff.urgent_unverified, handoff.claimed_unverified, handoff.not_acknowledged,
                    handoff.blocked, handoff.uncertain_status, handoff.verified, handoff.closed_unresolvable):
        lines.extend(i.summary for i in section)
    lines.extend(reason for _, reason in handoff.hypotheses_needing_review)
    return lines


# --- the handoff record and its acceptance (append-only) ---


class ShiftEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    case_id: str
    event_id: str
    kind: Literal["handoff", "accepted"]
    actor: str
    to_actor: Optional[str] = None
    handoff_id: Optional[str] = None
    state_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    # Unlike state_digest (the rendered handoff view), this fingerprint is
    # computed from the persisted case rows while the transition holds the
    # database write lock. It is the concurrency fence used at acceptance.
    state_fingerprint: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    note: str = Field(default="", max_length=4000)
    transfer: tuple[tuple[str, str], ...] = ()  # (requirement_id, revision at handoff)
    transferred: tuple[str, ...] = ()
    not_transferred: tuple[tuple[str, str], ...] = ()  # (requirement_id, why)
    state_changed_since_handoff: Optional[bool] = None
    recorded_at: datetime


class HandoffRejected(ValueError):
    pass


def _events(connection: sqlite3.Connection, case_id: str) -> list[ShiftEvent]:
    rows = connection.execute(
        "SELECT event_json FROM shift_events WHERE case_id=? ORDER BY seq", (case_id,)
    ).fetchall()
    return [ShiftEvent.model_validate_json(row[0]) for row in rows]


def list_shift_events(store: KrakadylStore, case_id: str) -> list[ShiftEvent]:
    return store.read_locked(lambda connection: _events(connection, case_id))


def _insert(connection: sqlite3.Connection, event: ShiftEvent, summary: str) -> None:
    now_iso = event.recorded_at.astimezone(timezone.utc).isoformat()
    connection.execute(
        "INSERT INTO shift_events (event_id, case_id, kind, event_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (event.event_id, event.case_id, event.kind, event.model_dump_json(), now_iso),
    )
    connection.execute(
        "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
        (event.case_id, now_iso, f"shift_{event.kind}", summary,
         json.dumps({"event_id": event.event_id, "handoff_id": event.handoff_id}, sort_keys=True)),
    )


_FINGERPRINT_IGNORED_TABLES = {"events", "acquisition_events", "shift_events", "counterfactuals"}


def _state_fingerprint(connection: sqlite3.Connection, case_id: str) -> str:
    """Fingerprint case state without including audit rows created by handoff itself.

    The query runs inside the same transaction as record/accept. Dynamic table
    names come only from SQLite's schema catalogue; values remain bound
    parameters. This makes the fingerprint a database-level concurrency fence,
    not a caller-supplied snapshot.
    """
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    state = []
    for (table,) in tables:
        if table in _FINGERPRINT_IGNORED_TABLES:
            continue
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table.replace(chr(34), chr(34) * 2)}")')]
        if "case_id" not in columns:
            continue
        quoted = '"' + table.replace('"', '""') + '"'
        rows = connection.execute(
            f"SELECT * FROM {quoted} WHERE case_id=? ORDER BY rowid", (case_id,)
        ).fetchall()
        state.append({"table": table, "columns": columns, "rows": [list(row) for row in rows]})
    return hashlib.sha256(canonical_bytes(state)).hexdigest()


def record_handoff(
    store: KrakadylStore,
    *,
    case_id: str,
    from_actor: str,
    to_actor: str,
    known_identities: set[str],
    seen_state_digest: str,
    current: ShiftHandoff,
    transfer_requirement_ids: tuple[str, ...],
    note: str,
    now: datetime,
) -> ShiftEvent:
    """`current` is the handoff view computed for this request; the
    outgoing person must have been looking at exactly that state."""
    if current.case_id != case_id:
        raise HandoffRejected("the handoff view belongs to a different case")
    if to_actor == from_actor:
        raise HandoffRejected("a handoff goes to someone else")
    if to_actor not in known_identities:
        raise HandoffRejected(f"'{to_actor}' is not a configured operator")
    if seen_state_digest != current.state_digest:
        raise HandoffRejected("the case changed since you loaded the handoff view; review it again before handing off")

    def transition(connection: sqlite3.Connection) -> ShiftEvent:
        transfer = []
        for requirement_id in transfer_requirement_ids:
            row = connection.execute(
                "SELECT json FROM objects WHERE case_id=? AND kind='requirement' AND obj_id=?",
                (case_id, requirement_id),
            ).fetchone()
            if row is None:
                raise HandoffRejected(f"no requirement '{requirement_id}' in this case")
            requirement = EvidenceRequirement.model_validate_json(row[0])
            if requirement.responsibility.owner != from_actor:
                raise HandoffRejected(f"'{requirement_id}' is owned by {requirement.responsibility.owner}, not you")
            if requirement.resolved or requirement.unresolvable:
                raise HandoffRejected(f"'{requirement_id}' is already closed; nothing to hand over")
            transfer.append((requirement_id, requirement_revision_digest(requirement)))
        event = ShiftEvent(
            case_id=case_id, event_id=f"handoff-{secrets.token_hex(8)}", kind="handoff",
            actor=from_actor, to_actor=to_actor, state_digest=current.state_digest,
            state_fingerprint=_state_fingerprint(connection, case_id),
            note=note, transfer=tuple(transfer), recorded_at=now,
        )
        _insert(connection, event, f"{from_actor} handed the case to {to_actor}"
                + (f" with {len(transfer)} requirement(s) to take over" if transfer else ""))
        return event

    return store.atomic_write(transition)


def accept_handoff(
    store: KrakadylStore,
    *,
    case_id: str,
    handoff_id: str,
    actor: str,
    current: ShiftHandoff,
    now: datetime,
) -> ShiftEvent:
    """Accepting is taking responsibility: each transferred requirement
    whose state did not move since the handoff becomes the incoming
    person's, ACKNOWLEDGED by them (REPORTED_DONE, BLOCKED and UNKNOWN
    keep their status — they describe the work, not who holds it). Anything that moved is listed as
    not transferred, with the reason, rather than handed over blind."""

    if current.case_id != case_id:
        raise HandoffRejected("the handoff view belongs to a different case")

    def transition(connection: sqlite3.Connection) -> ShiftEvent:
        events = _events(connection, case_id)
        handoff = next((e for e in events if e.kind == "handoff" and e.event_id == handoff_id), None)
        if handoff is None:
            raise HandoffRejected("no such handoff in this case")
        if handoff.to_actor != actor:
            raise HandoffRejected(f"this handoff is addressed to {handoff.to_actor}")
        if any(e.kind == "accepted" and e.handoff_id == handoff_id for e in events):
            raise HandoffRejected("this handoff was already accepted")
        if handoff.state_fingerprint is None:
            raise HandoffRejected("this handoff predates transaction-bound state fencing; create a new handoff")
        live_state_fingerprint = _state_fingerprint(connection, case_id)
        transferred, not_transferred = [], []
        now_iso = now.astimezone(timezone.utc).isoformat()
        for requirement_id, revision in handoff.transfer:
            row = connection.execute(
                "SELECT json FROM objects WHERE case_id=? AND kind='requirement' AND obj_id=?",
                (case_id, requirement_id),
            ).fetchone()
            if row is None:
                not_transferred.append((requirement_id, "requirement no longer exists"))
                continue
            requirement = EvidenceRequirement.model_validate_json(row[0])
            if requirement_revision_digest(requirement) != revision:
                not_transferred.append((requirement_id, "changed after the handoff; review it with the previous owner"))
                continue
            # Statuses that carry information about the work itself stay
            # as they are (red team L4-F2): handing over a blocked or
            # unknown item must not make it look freshly acknowledged.
            keep_status = requirement.responsibility.status in (
                TaskStatus.REPORTED_DONE, TaskStatus.BLOCKED, TaskStatus.UNKNOWN
            )
            responsibility = TaskResponsibility(**{
                **requirement.responsibility.model_dump(),
                "owner": actor,
                "status": requirement.responsibility.status if keep_status else TaskStatus.ACKNOWLEDGED,
                "accepted_by": actor,
                "accepted_at": now,
            })
            updated = EvidenceRequirement(**{**requirement.model_dump(), "responsibility": responsibility.model_dump()})
            connection.execute(
                "UPDATE objects SET json=?, updated_at=? WHERE case_id=? AND kind='requirement' AND obj_id=?",
                (updated.model_dump_json(), now_iso, case_id, requirement_id),
            )
            transferred.append(requirement_id)
        event = ShiftEvent(
            case_id=case_id, event_id=f"accepted-{secrets.token_hex(8)}", kind="accepted", actor=actor,
            handoff_id=handoff_id, state_digest=current.state_digest,
            state_fingerprint=live_state_fingerprint,
            transferred=tuple(transferred), not_transferred=tuple(not_transferred),
            state_changed_since_handoff=live_state_fingerprint != handoff.state_fingerprint, recorded_at=now,
        )
        _insert(connection, event, f"{actor} accepted the handoff from {handoff.actor}"
                + (f"; {len(not_transferred)} requirement(s) not transferred because they changed" if not_transferred else ""))
        return event

    return store.atomic_write(transition)
