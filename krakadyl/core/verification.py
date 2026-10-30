"""Validation of structured verification dependencies.

This is deliberately separate from the policy engine: it answers whether the
evidence basis is still valid, not whether the mandate permits the action.
Legacy requirements without structured records remain supported but do not
claim graph-level independence; callers can surface that limitation explicitly.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from krakadyl.core.models import EvidenceRequirement, Observation
from krakadyl.store import KrakadylStore


class VerificationInvalidationRejected(ValueError):
    pass


def _file_matches(observation: Observation, path: Path) -> bool:
    if observation.digest != observation.evidence_custody.integrity_digest or not path.exists():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == observation.evidence_custody.integrity_digest


def validate_verification_dependencies(
    requirement: EvidenceRequirement,
    observations: list[Observation],
    observation_files: dict[str, Path],
) -> tuple[str, ...]:
    """Return deterministic failure reasons for the requirement's graph.

    An empty tuple means that all structured dependencies are present and their
    current bytes match the digests recorded by the observations. Requirements
    without structured records return no failures for backward compatibility;
    that is a documented legacy limitation, not proof of graph-level validity.
    """
    if not requirement.verification_records:
        return ()

    by_id = {observation.id: observation for observation in observations}
    records_by_id = {record.verification_id: record for record in requirement.verification_records}
    failures: list[str] = []
    checked_sources: set[tuple[str, str]] = set()
    active: set[str] = set()

    for record in requirement.verification_records:
        target = by_id.get(record.target_observation_id)
        if target is None:
            failures.append(f"verification target '{record.target_observation_id}' is absent")
        elif target.invalidated:
            failures.append(
                f"verification target '{target.id}' is invalidated: {target.invalidation_reason}"
            )
        elif not _file_matches(target, observation_files.get(target.id, Path("/nonexistent"))):
            failures.append(f"verification target '{target.id}' failed integrity")

    def closure(record_id: str) -> set[str]:
        if record_id in active:
            failures.append(f"verification dependency cycle at '{record_id}'")
            return set()
        record = records_by_id.get(record_id)
        if record is None:
            failures.append(f"verification parent '{record_id}' is absent")
            return set()
        active.add(record_id)
        sources: set[str] = set()
        for basis in record.basis:
            sources.add(basis.observation_id)
            marker = (basis.observation_id, basis.observation_digest)
            if marker in checked_sources:
                continue
            checked_sources.add(marker)
            observation = by_id.get(basis.observation_id)
            if observation is None:
                failures.append(f"verification source '{basis.observation_id}' is absent")
                continue
            if observation.invalidated:
                failures.append(
                    f"verification source '{basis.observation_id}' is invalidated: "
                    f"{observation.invalidation_reason}"
                )
                continue
            if observation.digest != basis.observation_digest:
                failures.append(f"verification source '{basis.observation_id}' digest changed")
                continue
            if not _file_matches(observation, observation_files.get(observation.id, Path("/nonexistent"))):
                failures.append(f"verification source '{basis.observation_id}' failed integrity")
        for parent_id in record.parent_verification_ids:
            sources.update(closure(parent_id))
        active.remove(record_id)
        return sources

    referenced_ids = {
        parent
        for record in requirement.verification_records
        for parent in record.parent_verification_ids
    }
    roots = [record for record in requirement.verification_records if record.verification_id not in referenced_ids]
    root_sources = [closure(record.verification_id) for record in roots]
    for index, first in enumerate(root_sources):
        for second in root_sources[index + 1:]:
            shared = first.intersection(second)
            if shared:
                failures.append(
                    "independent verification roots share primary source(s): "
                    + ", ".join(sorted(shared))
                )
    return tuple(dict.fromkeys(failures))


def invalidate_observation(
    store: KrakadylStore,
    *,
    case_id: str,
    observation_id: str,
    actor_identity: str,
    reason: str,
    now: datetime,
) -> Observation:
    """Atomically mark a source invalid and append the causal event.

    Requirements are intentionally not rewritten here. Structured verification
    consumers discover the invalid source at the next policy check, so an
    invalidation cannot be hidden by leaving derived requirement JSON untouched.
    """
    if not actor_identity.strip():
        raise VerificationInvalidationRejected("an invalidation needs an authenticated actor")
    if not reason.strip():
        raise VerificationInvalidationRejected("an invalidation needs a stated reason")
    if now.utcoffset() is None:
        raise VerificationInvalidationRejected("invalidation timestamp must include a timezone")
    now_iso = now.astimezone(timezone.utc).isoformat()

    def transition(connection: sqlite3.Connection) -> Observation:
        row = connection.execute(
            "SELECT json FROM objects WHERE case_id=? AND kind='observation' AND obj_id=?",
            (case_id, observation_id),
        ).fetchone()
        if row is None:
            raise VerificationInvalidationRejected("observation does not exist in this case")
        observation = Observation.model_validate_json(row[0])
        if observation.invalidated:
            raise VerificationInvalidationRejected("observation is already invalidated")
        invalidated = Observation(**{
            **observation.model_dump(),
            "invalidated": True,
            "invalidation_reason": reason.strip(),
        })
        connection.execute(
            "UPDATE objects SET json=?, updated_at=? WHERE case_id=? AND kind='observation' AND obj_id=?",
            (invalidated.model_dump_json(), now_iso, case_id, observation_id),
        )
        connection.execute(
            "INSERT INTO events (case_id, ts, kind, summary, detail_json) VALUES (?, ?, ?, ?, ?)",
            (
                case_id,
                now_iso,
                "observation_invalidated",
                f"{actor_identity} invalidated observation {observation_id}: {reason.strip()}",
                json.dumps({
                    "observation_id": observation_id,
                    "actor_identity": actor_identity,
                    "reason": reason.strip(),
                }, sort_keys=True),
            ),
        )
        return invalidated

    return store.atomic_write(transition)
