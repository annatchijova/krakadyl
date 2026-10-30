"""Level 4 — shared custody: what each teammate says, kept apart from what is verified.

Level 2's invalidation engine reacted to time and to new evidence. Here
"what changed" is a teammate's statement: "I preserved it", "I'm blocked",
"that isn't done", "I checked their work". Every such statement is an
append-only `TeamRecord` bound to a proven identity and to the exact
requirement revision its author was looking at. Nothing is overwritten;
a correction is a new record that refers to the old one.

What a record may change is narrow and stated here, once:

| Record | Who | Effect on the requirement |
|---|---|---|
| ACKNOWLEDGED | the owner only | ASSIGNED -> ACKNOWLEDGED |
| REPORTED_DONE | anyone | -> REPORTED_DONE (a claim; the first claimant stays on record) |
| BLOCKED | anyone | owner: -> BLOCKED; others: recorded, no state change |
| VERIFIED | not the claimant | -> resolved, VERIFIED_DONE — only with no open conflict |
| DISPUTED | anyone | none; opens a conflict |
| RESOLUTION | not a party to the conflict | closes it; `reopen_requirement` -> UNKNOWN, unresolved |

Attaching evidence to a claim does not verify it (invariant 4: nobody
verifies their own work). Attached references are integrity-checked when
recorded and re-checked every time conflicts are computed; a claim whose
evidence no longer matches becomes a conflict, not a quiet footnote.

Conflicts are derived, never stored: `find_conflicts` recomputes them
from the records on every read, so there is no second copy of the truth
to drift. Their wording describes the case, never a person — see
`BLAME_TERMS` and `docs/levels.md`, "No individual blame, by construction".
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from krakadyl.core.acquisition import requirement_revision_digest
from krakadyl.core.models import EvidenceRequirement, TaskResponsibility, TaskStatus
from krakadyl.core.receipt import canonical_bytes
from krakadyl.store import KrakadylStore

# Words that describe a person's competence or fault rather than the state
# of the case. Generated text in this module must never contain them; a
# test scans every conflict and handoff string against this list.
BLAME_TERMS = (
    "blame", "fault", "careless", "negligent", "negligence", "incompetent", "lazy",
    "failed to", "forgot", "should have", "mistake by", "error by",
    "culpa", "negligente", "negligencia", "incompetente", "descuido", "se olvidó", "debería haber",
)


class ClaimKind(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    REPORTED_DONE = "reported_done"
    BLOCKED = "blocked"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    RESOLUTION = "resolution"


class ConflictKind(str, Enum):
    COMPETING_COMPLETION = "competing_completion"
    DISPUTED = "disputed"
    EVIDENCE_MISMATCH = "evidence_mismatch"
    STATUS_CONTRADICTION = "status_contradiction"


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["observation", "acquired_observation"]
    ref_id: str = Field(min_length=1, max_length=256)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class TeamRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    case_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    kind: ClaimKind
    actor: str = Field(min_length=1)
    statement: str = Field(min_length=1, max_length=4000)
    evidence_refs: tuple[EvidenceRef, ...] = ()
    refers_to: tuple[str, ...] = ()
    verification_method: Optional[str] = Field(default=None, max_length=256)
    resolves_conflict_id: Optional[str] = None
    decision: Optional[Literal["keep_current_state", "reopen_requirement"]] = None
    requirement_revision_seen: str = Field(pattern=r"^[a-f0-9]{64}$")
    recorded_at: datetime

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> TeamRecord:
        if self.recorded_at.utcoffset() is None:
            raise ValueError("record timestamp must include a timezone")
        if len(set(self.refers_to)) != len(self.refers_to):
            raise ValueError("referenced records must be unique")
        if len({(r.kind, r.ref_id) for r in self.evidence_refs}) != len(self.evidence_refs):
            raise ValueError("evidence references must be unique")
        if self.kind == ClaimKind.VERIFIED:
            if len(self.refers_to) != 1 or not self.verification_method:
                raise ValueError("a verification names exactly one claim and how it was checked")
            if self.verification_method.strip().lower().startswith("tool:"):
                # 'tool:' marks automated checks (models.TaskResponsibility);
                # a person must not be able to label their check as one.
                raise ValueError("'tool:' verification methods are reserved for automated checks")
        elif self.verification_method is not None:
            raise ValueError("only a verification carries a verification method")
        if self.kind == ClaimKind.DISPUTED and not self.refers_to:
            raise ValueError("a dispute names the record(s) it disputes")
        if self.kind == ClaimKind.RESOLUTION:
            if not self.resolves_conflict_id or self.decision is None or not self.refers_to:
                raise ValueError("a resolution names its conflict, the records in it, and a decision")
        elif self.resolves_conflict_id is not None or self.decision is not None:
            raise ValueError("only a resolution carries a conflict id and decision")
        if self.kind in (ClaimKind.ACKNOWLEDGED, ClaimKind.BLOCKED, ClaimKind.REPORTED_DONE) and self.refers_to:
            raise ValueError(f"a {self.kind.value} record does not refer to other records")
        return self


class Conflict(BaseModel):
    model_config = ConfigDict(frozen=True)

    conflict_id: str
    requirement_id: str
    kind: ConflictKind
    record_ids: tuple[str, ...]
    parties: tuple[str, ...]
    description: str


class TeamRejected(ValueError):
    pass


# Returns None when the reference resolves to an intact record, otherwise why not.
RefChecker = Callable[[EvidenceRef], Optional[str]]


def _conflict_id(kind: ConflictKind, record_ids) -> str:
    payload = json.dumps([kind.value, sorted(record_ids)], separators=(",", ":"))
    return "conflict-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _latest_by_actor(records: list[TeamRecord], kinds: set[ClaimKind]) -> dict[str, TeamRecord]:
    latest: dict[str, TeamRecord] = {}
    for record in records:
        if record.kind in kinds:
            latest[record.actor] = record
    return latest


def find_conflicts(
    requirement_id: str, records: list[TeamRecord], check_ref: RefChecker
) -> tuple[list[Conflict], list[Conflict]]:
    """(open, resolved) conflicts for one requirement, recomputed from
    the records in their recorded order. Pure apart from `check_ref`."""
    records = [r for r in records if r.requirement_id == requirement_id]
    by_id = {r.record_id: r for r in records}
    found: dict[str, Conflict] = {}

    def add(kind: ConflictKind, involved: list[TeamRecord], description: str) -> None:
        ids = tuple(sorted(r.record_id for r in involved))
        conflict_id = _conflict_id(kind, ids)
        found[conflict_id] = Conflict(
            conflict_id=conflict_id, requirement_id=requirement_id, kind=kind, record_ids=ids,
            parties=tuple(sorted({r.actor for r in involved})), description=description,
        )

    completions = [r for r in records if r.kind == ClaimKind.REPORTED_DONE and r.evidence_refs]
    for i, first in enumerate(completions):
        for second in completions[i + 1:]:
            if first.actor != second.actor and set(first.evidence_refs) != set(second.evidence_refs):
                add(ConflictKind.COMPETING_COMPLETION, [first, second],
                    f"two completion claims for {requirement_id} cite different evidence; "
                    "which artifact satisfies it is undetermined")

    for record in records:
        if record.kind == ClaimKind.DISPUTED:
            disputed = [by_id[i] for i in record.refers_to if i in by_id]
            add(ConflictKind.DISPUTED, [record, *disputed],
                f"a recorded statement disputes {len(disputed)} earlier record(s) on {requirement_id}")

    for record in records:
        if record.kind in (ClaimKind.REPORTED_DONE, ClaimKind.VERIFIED):
            problems = [p for p in (check_ref(ref) for ref in record.evidence_refs) if p]
            if problems:
                add(ConflictKind.EVIDENCE_MISMATCH, [record],
                    f"evidence cited for {requirement_id} no longer matches what was recorded: {problems[0]}")

    latest = _latest_by_actor(records, {ClaimKind.REPORTED_DONE, ClaimKind.BLOCKED})
    blocked = [r for r in latest.values() if r.kind == ClaimKind.BLOCKED]
    done = [r for r in latest.values() if r.kind == ClaimKind.REPORTED_DONE]
    for b in blocked:
        for d in done:
            add(ConflictKind.STATUS_CONTRADICTION, [b, d],
                f"current statements on {requirement_id} disagree: one reports it blocked, another reports it done")

    resolved_ids = {
        r.resolves_conflict_id for r in records
        if r.kind == ClaimKind.RESOLUTION
    }
    open_conflicts = [c for cid, c in found.items() if cid not in resolved_ids]
    closed = [c for cid, c in found.items() if cid in resolved_ids]
    return open_conflicts, closed


def conflicted_requirement_ids(
    requirement_ids, records: list[TeamRecord], check_ref: RefChecker
) -> frozenset[str]:
    return frozenset(
        rid for rid in requirement_ids if find_conflicts(rid, records, check_ref)[0]
    )


# --- persistence and the one transition function ---


def _utc_iso(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


def _records(connection: sqlite3.Connection, case_id: str, requirement_id: Optional[str] = None) -> list[TeamRecord]:
    query = "SELECT record_json FROM team_records WHERE case_id=?"
    params: tuple = (case_id,)
    if requirement_id is not None:
        query += " AND requirement_id=?"
        params += (requirement_id,)
    rows = connection.execute(query + " ORDER BY seq", params).fetchall()
    return [TeamRecord.model_validate_json(row[0]) for row in rows]


def list_team_records(store: KrakadylStore, case_id: str) -> list[TeamRecord]:
    return store.read_locked(lambda connection: _records(connection, case_id))


def _responsibility(requirement: EvidenceRequirement, **changes) -> dict:
    return TaskResponsibility(**{**requirement.responsibility.model_dump(), **changes}).model_dump()


def _transition(
    requirement: EvidenceRequirement,
    record: TeamRecord,
    existing: list[TeamRecord],
    open_conflicts: list[Conflict],
) -> EvidenceRequirement:
    """Pure: the requirement after `record`, or TeamRejected. See the module table."""
    r = requirement
    status = r.responsibility.status
    by_id = {x.record_id: x for x in existing}
    closed = r.resolved or r.unresolvable

    if record.kind == ClaimKind.ACKNOWLEDGED:
        if record.actor != r.responsibility.owner:
            raise TeamRejected(f"only the owner ({r.responsibility.owner}) can acknowledge this requirement")
        if status != TaskStatus.ASSIGNED:
            raise TeamRejected(f"requirement is '{status.value}', not 'assigned'")
        return EvidenceRequirement(**{**r.model_dump(), "responsibility": _responsibility(
            r, status=TaskStatus.ACKNOWLEDGED, accepted_by=record.actor, accepted_at=record.recorded_at)})

    if record.kind == ClaimKind.REPORTED_DONE:
        if closed:
            raise TeamRejected("requirement is already resolved or closed as unresolvable")
        if status == TaskStatus.REPORTED_DONE:
            return r  # first claimant stays; this claim is kept as its own record
        return EvidenceRequirement(**{**r.model_dump(), "responsibility": _responsibility(
            r, status=TaskStatus.REPORTED_DONE, reported_done_by=record.actor,
            reported_done_at=record.recorded_at)})

    if record.kind == ClaimKind.BLOCKED:
        if closed:
            raise TeamRejected("requirement is already resolved or closed as unresolvable")
        if record.actor != r.responsibility.owner:
            return r
        return EvidenceRequirement(**{**r.model_dump(), "responsibility": _responsibility(
            r, status=TaskStatus.BLOCKED)})

    if record.kind == ClaimKind.VERIFIED:
        if closed:
            raise TeamRejected("requirement is already resolved or closed as unresolvable")
        claim = by_id.get(record.refers_to[0])
        if claim is None or claim.kind != ClaimKind.REPORTED_DONE:
            raise TeamRejected("a verification must name a completion claim on this requirement")
        if record.actor in {claim.actor, r.responsibility.reported_done_by}:
            raise TeamRejected("verification must come from someone other than the claimant")
        if open_conflicts:
            raise TeamRejected(
                f"{len(open_conflicts)} open conflict(s) on this requirement must be resolved before it can be verified"
            )
        refs = sorted({ref.digest[:16] for ref in (*claim.evidence_refs, *record.evidence_refs)})
        return EvidenceRequirement(**{**r.model_dump(), "resolved": True, "responsibility": _responsibility(
            r, status=TaskStatus.VERIFIED_DONE,
            reported_done_by=r.responsibility.reported_done_by or claim.actor,
            reported_done_at=r.responsibility.reported_done_at or claim.recorded_at,
            verified_by=record.actor, verified_at=record.recorded_at,
            verification_method=f"peer-verification:{record.verification_method}",
            verified_against=f"{record.record_id} confirming {claim.record_id}"
            + (f"; evidence sha256:{', '.join(refs)}" if refs else ""),
        )})

    if record.kind == ClaimKind.DISPUTED:
        targets = [by_id.get(i) for i in record.refers_to]
        if any(t is None or t.kind not in (ClaimKind.REPORTED_DONE, ClaimKind.VERIFIED) for t in targets):
            raise TeamRejected("a dispute must name completion or verification records on this requirement")
        return r

    if record.kind == ClaimKind.RESOLUTION:
        conflict = next((c for c in open_conflicts if c.conflict_id == record.resolves_conflict_id), None)
        if conflict is None:
            raise TeamRejected("no such open conflict on this requirement")
        if tuple(sorted(record.refers_to)) != conflict.record_ids:
            raise TeamRejected("a resolution must name exactly the records in the conflict")
        if record.actor in conflict.parties:
            raise TeamRejected("a conflict is resolved by someone who is not a party to it")
        if record.decision == "keep_current_state":
            if conflict.kind == ConflictKind.EVIDENCE_MISMATCH:
                raise TeamRejected("evidence that no longer matches cannot be kept as is; reopen the requirement")
            return r
        return EvidenceRequirement(**{
            **r.model_dump(), "resolved": False, "unresolvable": False, "unresolvable_reason": None,
            "responsibility": _responsibility(
                r, status=TaskStatus.UNKNOWN, verified_by=None, verified_at=None,
                verification_method=None, verified_against=None),
        })

    raise TeamRejected(f"unsupported record kind {record.kind}")


def record_team_statement(
    store: KrakadylStore,
    *,
    case_id: str,
    requirement_id: str,
    kind: ClaimKind,
    actor: str,
    statement: str,
    expected_requirement_revision: str,
    check_ref: RefChecker,
    now: datetime,
    evidence_refs: tuple[EvidenceRef, ...] = (),
    refers_to: tuple[str, ...] = (),
    verification_method: Optional[str] = None,
    resolves_conflict_id: Optional[str] = None,
    decision: Optional[str] = None,
) -> tuple[TeamRecord, EvidenceRequirement]:
    """`actor` must already be a proven identity. One transaction: re-read
    the requirement, compare the revision its author saw, check every
    cited artifact, append the record, apply the transition, log it."""
    now_iso = _utc_iso(now)

    def transition(connection: sqlite3.Connection):
        row = connection.execute(
            "SELECT json FROM objects WHERE case_id=? AND kind='requirement' AND obj_id=?",
            (case_id, requirement_id),
        ).fetchone()
        if row is None:
            raise TeamRejected("requirement does not exist in this case")
        requirement = EvidenceRequirement.model_validate_json(row[0])
        if requirement_revision_digest(requirement) != expected_requirement_revision:
            raise TeamRejected("requirement changed since it was shown; reload before recording")
        try:
            record = TeamRecord(
                case_id=case_id, record_id=f"team-{secrets.token_hex(8)}", requirement_id=requirement_id,
                kind=kind, actor=actor, statement=statement, evidence_refs=evidence_refs,
                refers_to=refers_to, verification_method=verification_method,
                resolves_conflict_id=resolves_conflict_id, decision=decision,
                requirement_revision_seen=expected_requirement_revision, recorded_at=now,
            )
        except ValueError as exc:
            raise TeamRejected(str(exc)) from exc
        for ref in record.evidence_refs:
            problem = check_ref(ref)
            if problem:
                raise TeamRejected(f"cited evidence {ref.kind} '{ref.ref_id}' cannot be used: {problem}")
        existing = _records(connection, case_id, requirement_id)
        open_conflicts, _ = find_conflicts(requirement_id, existing, check_ref)
        updated = _transition(requirement, record, existing, open_conflicts)
        connection.execute(
            "INSERT INTO team_records (record_id, case_id, requirement_id, kind, actor, record_json, record_digest, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (record.record_id, case_id, requirement_id, kind.value, actor, record.model_dump_json(),
             _record_digest(record), now_iso),
        )
        if updated != requirement:
            connection.execute(
                "UPDATE objects SET json=?, updated_at=? WHERE case_id=? AND kind='requirement' AND obj_id=?",
                (updated.model_dump_json(), now_iso, case_id, requirement_id),
            )
        connection.execute(
            "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
            (case_id, now_iso, f"team_{kind.value}",
             f"{actor} recorded '{kind.value}' on {requirement_id}"
             + (f" (requirement now {updated.responsibility.status.value})" if updated != requirement else ""),
             json.dumps({"record_id": record.record_id, "requirement_id": requirement_id}, sort_keys=True)),
        )
        return record, updated

    return store.atomic_write(transition)


def _record_digest(record: TeamRecord) -> str:
    return hashlib.sha256(canonical_bytes(record.model_dump(mode="json"))).hexdigest()
