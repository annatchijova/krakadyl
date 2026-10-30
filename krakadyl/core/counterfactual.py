"""Level 5 — comparable routes: what the case would allow under different limits.

A counterfactual is a closed, typed set of assumptions ("if device-B were
in the mandate", "if req-a2 were independently verified", "if the
conflict on req-a1 were resolved") applied to *copies* of the case's
inputs, then run through the unmodified pipeline — `check_mandate`,
`check_evidence`, `decide` via `prepare_evidence_package`, and
`next_move`. Nothing new decides anything.

It is measured, not narrated: the real outcome and the hypothetical one
are computed side by side, and every assumption is tested for whether it
is *necessary* (dropping it alone changes the hypothetical verdict) and
whether it is *sufficient alone* (it alone changes the real verdict).

It is kept apart from the case by construction:

- Results live in their own append-only table, never in `objects`, so no
  code path that reads case state can see them.
- No `PreparedAction` survives: whatever the pipeline prepares on the
  copy is discarded, so a counterfactual is never executable.
- Each result carries the digest of the real inputs it was computed
  from; once the case moves, it is reported as stale rather than shown
  as if it still described the case.

Deliberately not modelable: "assume this file is intact". Integrity is a
fact about bytes, read from disk; a hypothetical that pretends tampered
bytes are fine would invite exactly the reasoning KRAKADYL exists to stop.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from krakadyl.core.continuity import next_move
from krakadyl.core.executor import prepare_evidence_package, verify_observation_integrity
from krakadyl.core.models import (
    AuthorityState,
    AuthorityVerdict,
    EvidenceRequirement,
    EvidenceState,
    Mandate,
    Observation,
    ProposedAction,
    TaskResponsibility,
    TaskStatus,
)
from krakadyl.core.receipt import canonical_bytes
from krakadyl.store import KrakadylStore

MAX_DELTAS = 8


class DeltaKind(str, Enum):
    GRANT_RESOURCE = "grant_resource"
    GRANT_OPERATION = "grant_operation"
    GRANT_DESTINATION = "grant_destination"
    EXTEND_MANDATE_UNTIL = "extend_mandate_until"
    MANDATE_NOT_REVOKED = "mandate_not_revoked"
    REQUIREMENT_VERIFIED = "requirement_verified"
    REQUIREMENT_UNRESOLVABLE = "requirement_unresolvable"
    CONFLICT_RESOLVED = "conflict_resolved"
    SOURCE_AVAILABLE = "source_available"


_AUTHORITY = {DeltaKind.GRANT_RESOURCE, DeltaKind.GRANT_OPERATION, DeltaKind.GRANT_DESTINATION,
              DeltaKind.EXTEND_MANDATE_UNTIL, DeltaKind.MANDATE_NOT_REVOKED}
_NEEDS_VALUE = {DeltaKind.GRANT_RESOURCE, DeltaKind.GRANT_OPERATION, DeltaKind.GRANT_DESTINATION}
_NEEDS_REQUIREMENT = {DeltaKind.REQUIREMENT_VERIFIED, DeltaKind.REQUIREMENT_UNRESOLVABLE,
                      DeltaKind.CONFLICT_RESOLVED, DeltaKind.SOURCE_AVAILABLE}


class Delta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: DeltaKind
    value: Optional[str] = Field(default=None, min_length=1, max_length=256)
    requirement_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    until: Optional[datetime] = None

    @model_validator(mode="after")
    def _fields_match_kind(self) -> Delta:
        wants_value = self.kind in _NEEDS_VALUE
        wants_requirement = self.kind in _NEEDS_REQUIREMENT
        wants_until = self.kind == DeltaKind.EXTEND_MANDATE_UNTIL
        if (self.value is not None) != wants_value:
            raise ValueError(f"'{self.kind.value}' {'needs' if wants_value else 'takes no'} value")
        if (self.requirement_id is not None) != wants_requirement:
            raise ValueError(f"'{self.kind.value}' {'needs' if wants_requirement else 'takes no'} requirement_id")
        if (self.until is not None) != wants_until:
            raise ValueError(f"'{self.kind.value}' {'needs' if wants_until else 'takes no'} until")
        if self.until is not None and self.until.utcoffset() is None:
            raise ValueError("'until' must include a timezone")
        return self

    def label(self) -> str:
        target = self.value or self.requirement_id or (self.until.isoformat() if self.until else "")
        return f"{self.kind.value}({target})" if target else self.kind.value


class Question(BaseModel):
    """The action asked about — today the one domain action, package export."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["package_export"] = "package_export"
    allowed_device: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    destination: str = Field(min_length=1, max_length=256)


class Outcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: AuthorityVerdict
    evidence_state: EvidenceState
    authority_state: AuthorityState
    reasons: tuple[str, ...]
    would_include: tuple[str, ...]
    next_move_primary: Optional[str]
    next_move_uncertain: bool


class DeltaEffect(BaseModel):
    model_config = ConfigDict(frozen=True)

    delta: Delta
    necessary: bool        # dropping only this delta changes the hypothetical verdict
    sufficient_alone: bool  # this delta alone changes the real verdict


class Counterfactual(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    hypothetical: Literal[True] = True
    counterfactual_id: str
    case_id: str
    created_by: str
    created_at: datetime
    question: Question
    deltas: tuple[Delta, ...]
    base_state_digest: str
    real: Outcome
    hypothetical_outcome: Outcome
    verdict_changed: bool
    effects: tuple[DeltaEffect, ...]
    caveat: str = (
        "Hypothetical. Computed on copies of the case's inputs under the stated assumptions; "
        "never applied to the case and never executable. Each assumption is a limit someone "
        "would have to change for real, through the normal authority and verification paths."
    )


class CaseInputs(BaseModel):
    """Everything the pipeline reads, as plain data. `integrity` is read
    from disk by the caller and is never altered by a delta."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    case_id: str
    mandate: Mandate
    observations: list[Observation]
    requirements: list[EvidenceRequirement]
    observation_files: dict[str, Path]
    conflicted_requirement_ids: frozenset[str]
    resolvable_requirement_ids: frozenset[str]


class CounterfactualRejected(ValueError):
    pass


def _validate(inputs: CaseInputs, deltas: tuple[Delta, ...]) -> None:
    if not deltas:
        raise CounterfactualRejected("a counterfactual needs at least one assumption")
    if len(deltas) > MAX_DELTAS:
        raise CounterfactualRejected(f"at most {MAX_DELTAS} assumptions per counterfactual")
    if len(set(deltas)) != len(deltas):
        raise CounterfactualRejected("assumptions must be distinct")
    requirement_ids = {r.id for r in inputs.requirements}
    for delta in deltas:
        if delta.requirement_id is not None and delta.requirement_id not in requirement_ids:
            raise CounterfactualRejected(f"no requirement '{delta.requirement_id}' in this case")
    verified = {d.requirement_id for d in deltas if d.kind == DeltaKind.REQUIREMENT_VERIFIED}
    closed = {d.requirement_id for d in deltas if d.kind == DeltaKind.REQUIREMENT_UNRESOLVABLE}
    if verified & closed:
        raise CounterfactualRejected("a requirement cannot be assumed both verified and unresolvable")


def _apply(inputs: CaseInputs, deltas: tuple[Delta, ...]) -> CaseInputs:
    """Copies only. Mandates are rebuilt through their constructor with a
    marked revision; requirements likewise, so every validator still runs."""
    m = inputs.mandate.model_dump()
    touched_mandate = False
    for d in deltas:
        if d.kind in _AUTHORITY:
            touched_mandate = True
        if d.kind == DeltaKind.GRANT_RESOURCE and d.value not in m["resources"]:
            m["resources"] = [*m["resources"], d.value]
        elif d.kind == DeltaKind.GRANT_OPERATION and d.value not in m["operations"]:
            m["operations"] = [*m["operations"], d.value]
        elif d.kind == DeltaKind.GRANT_DESTINATION and d.value not in m["destinations"]:
            m["destinations"] = [*m["destinations"], d.value]
        elif d.kind == DeltaKind.EXTEND_MANDATE_UNTIL:
            m["valid_until"] = d.until
        elif d.kind == DeltaKind.MANDATE_NOT_REVOKED:
            m["revoked"], m["revoked_reason"] = False, None
    if touched_mandate:
        m["revision"] = f"{m['revision']}+counterfactual"
    mandate = Mandate(**m)

    requirements = []
    for r in inputs.requirements:
        data = r.model_dump()
        for d in deltas:
            if d.requirement_id != r.id:
                continue
            if d.kind == DeltaKind.REQUIREMENT_VERIFIED:
                data["resolved"], data["unresolvable"], data["unresolvable_reason"] = True, False, None
                data["responsibility"] = TaskResponsibility(**{
                    **r.responsibility.model_dump(),
                    "status": TaskStatus.VERIFIED_DONE,
                    "verified_by": "counterfactual-assumption",
                    "verification_method": "counterfactual:assumed",
                    "verified_against": "nothing — assumed for this counterfactual only",
                }).model_dump()
            elif d.kind == DeltaKind.REQUIREMENT_UNRESOLVABLE:
                data["resolved"], data["unresolvable"] = False, True
                data["unresolvable_reason"] = "assumed for this counterfactual only"
        requirements.append(EvidenceRequirement(**data))

    return CaseInputs(
        case_id=inputs.case_id,
        mandate=mandate,
        observations=inputs.observations,
        requirements=requirements,
        observation_files=inputs.observation_files,
        conflicted_requirement_ids=inputs.conflicted_requirement_ids - {
            d.requirement_id for d in deltas if d.kind == DeltaKind.CONFLICT_RESOLVED
        },
        resolvable_requirement_ids=inputs.resolvable_requirement_ids | {
            d.requirement_id for d in deltas if d.kind == DeltaKind.SOURCE_AVAILABLE
        },
    )


def _outcome(inputs: CaseInputs, question: Question, now: datetime) -> Outcome:
    action = ProposedAction(
        id="counterfactual-probe", operation=question.operation,
        arguments={"device": question.allowed_device, "destination": question.destination},
        expected_effect="counterfactual evaluation only; never executed", mission_id=inputs.case_id,
    )
    decision, prepared = prepare_evidence_package(
        proposed_action=action, mandate=inputs.mandate, observations=inputs.observations,
        requirements=inputs.requirements, observation_files=inputs.observation_files,
        allowed_device=question.allowed_device, destination=question.destination, now=now,
        resolvable_requirement_ids=inputs.resolvable_requirement_ids,
        conflicted_requirement_ids=inputs.conflicted_requirement_ids,
    )
    move = next_move(inputs.requirements)
    return Outcome(
        verdict=decision.verdict,
        evidence_state=decision.evidence_state,
        authority_state=decision.authority_state,
        reasons=tuple(decision.reasons),
        # Only the ids are kept; the PreparedAction itself is discarded here
        # and never leaves this function, so nothing can execute it.
        would_include=tuple(prepared.resources_touched) if prepared is not None else (),
        next_move_primary=move.primary,
        next_move_uncertain=move.uncertain,
    )


def base_state_digest(inputs: CaseInputs, question: Question) -> str:
    integrity = {
        o.id: verify_observation_integrity(o, inputs.observation_files.get(o.id, Path("/nonexistent")))
        for o in inputs.observations
    }
    return hashlib.sha256(canonical_bytes({
        "digest_type": "counterfactual_base_state",
        "digest_version": 1,
        "question": question.model_dump(mode="json"),
        "mandate": inputs.mandate.model_dump(mode="json"),
        "observations": [o.model_dump(mode="json") for o in sorted(inputs.observations, key=lambda o: o.id)],
        "integrity": integrity,
        "requirements": [r.model_dump(mode="json") for r in sorted(inputs.requirements, key=lambda r: r.id)],
        "conflicted": sorted(inputs.conflicted_requirement_ids),
        "resolvable": sorted(inputs.resolvable_requirement_ids),
    })).hexdigest()


def evaluate_counterfactual(
    inputs: CaseInputs,
    question: Question,
    deltas: tuple[Delta, ...],
    *,
    created_by: str,
    now: datetime,
) -> Counterfactual:
    _validate(inputs, deltas)
    real = _outcome(inputs, question, now)
    hypothetical = _outcome(_apply(inputs, deltas), question, now)
    effects = []
    for delta in deltas:
        without = tuple(d for d in deltas if d != delta)
        if without:
            necessary = _outcome(_apply(inputs, without), question, now).verdict != hypothetical.verdict
        else:
            necessary = hypothetical.verdict != real.verdict
        alone = _outcome(_apply(inputs, (delta,)), question, now).verdict != real.verdict
        effects.append(DeltaEffect(delta=delta, necessary=necessary, sufficient_alone=alone))
    return Counterfactual(
        counterfactual_id=f"cf-{secrets.token_hex(8)}",
        case_id=inputs.case_id,
        created_by=created_by,
        created_at=now,
        question=question,
        deltas=deltas,
        base_state_digest=base_state_digest(inputs, question),
        real=real,
        hypothetical_outcome=hypothetical,
        verdict_changed=hypothetical.verdict != real.verdict,
        effects=tuple(effects),
    )


# --- storage: its own append-only table, never `objects` ---


def save_counterfactual(store: KrakadylStore, counterfactual: Counterfactual) -> None:
    def write(connection: sqlite3.Connection) -> None:
        now_iso = counterfactual.created_at.astimezone(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO counterfactuals (counterfactual_id, case_id, created_by, counterfactual_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (counterfactual.counterfactual_id, counterfactual.case_id, counterfactual.created_by,
             counterfactual.model_dump_json(), now_iso),
        )
        connection.execute(
            "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
            (counterfactual.case_id, now_iso, "counterfactual_evaluated",
             f"{counterfactual.created_by} evaluated a hypothetical "
             f"({', '.join(d.label() for d in counterfactual.deltas)}): "
             f"{counterfactual.real.verdict.value} would become {counterfactual.hypothetical_outcome.verdict.value} "
             "— not applied to the case",
             json.dumps({"counterfactual_id": counterfactual.counterfactual_id}, sort_keys=True)),
        )

    store.atomic_write(write)


def list_counterfactuals(store: KrakadylStore, case_id: str) -> list[Counterfactual]:
    rows = store.read_locked(lambda connection: connection.execute(
        "SELECT counterfactual_json FROM counterfactuals WHERE case_id=? ORDER BY seq", (case_id,)
    ).fetchall())
    return [Counterfactual.model_validate_json(row[0]) for row in rows]
