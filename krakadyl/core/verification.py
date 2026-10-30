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
from collections import Counter
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
    without structured records do not receive graph-level provenance checks,
    but duplicate observation IDs are still rejected because the namespace
    would otherwise be ambiguous to every consumer.
    """
    failures: list[str] = []
    duplicate_observation_ids = sorted(
        observation_id
        for observation_id, count in Counter(observation.id for observation in observations).items()
        if count > 1
    )
    failures.extend(
        f"duplicate observation id '{observation_id}' makes verification namespace ambiguous"
        for observation_id in duplicate_observation_ids
    )
    if not requirement.verification_records:
        return tuple(failures)

    duplicate_verification_ids = sorted(
        verification_id
        for verification_id, count in Counter(
            record.verification_id for record in requirement.verification_records
        ).items()
        if count > 1
    )
    failures.extend(
        f"duplicate verification id '{verification_id}' makes verification graph ambiguous"
        for verification_id in duplicate_verification_ids
    )
    duplicate_verifier_identities = sorted(
        verifier_identity
        for verifier_identity, count in Counter(
            record.verifier_identity for record in requirement.verification_records
        ).items()
        if count > 1
    )
    if duplicate_verifier_identities:
        failures.append(
            "verification records require distinct verifiers: "
            + ", ".join(duplicate_verifier_identities)
        )
    for record in requirement.verification_records:
        if not record.verification_id.strip():
            failures.append("verification ID must be non-empty")
        if not record.verifier_identity.strip():
            failures.append("verification identity must be non-empty")
        if record.recorded_at is None or record.recorded_at.utcoffset() is None:
            failures.append("verification timestamp must include a timezone")
        if not record.method.strip():
            failures.append("verification method must be non-empty")
        if not record.basis:
            failures.append(
                f"verification record has no primary basis: '{record.verification_id}'"
            )
        basis_ids = [basis.observation_id for basis in record.basis]
        if len(set(basis_ids)) != len(basis_ids):
            failures.append("verification basis observations must be unique")
        if len(set(record.parent_verification_ids)) != len(record.parent_verification_ids):
            failures.append("parent verification IDs must be unique")

    observation_dependencies: dict[str, set[str]] = {}
    for record in requirement.verification_records:
        dependencies = observation_dependencies.setdefault(record.target_observation_id, set())
        dependencies.update(
            basis.observation_id
            for basis in record.basis
            if basis.observation_id != record.target_observation_id
        )
    visiting_observations: set[str] = set()
    visited_observations: set[str] = set()

    def visit_observation(observation_id: str) -> None:
        if observation_id in visiting_observations:
            failures.append("observation dependency graph contains a cycle")
            return
        if observation_id in visited_observations:
            return
        visiting_observations.add(observation_id)
        for dependency_id in observation_dependencies.get(observation_id, set()):
            visit_observation(dependency_id)
        visiting_observations.remove(observation_id)
        visited_observations.add(observation_id)

    for observation_id in observation_dependencies:
        visit_observation(observation_id)

    by_id = {observation.id: observation for observation in observations}
    records_by_id = {record.verification_id: record for record in requirement.verification_records}
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
        elif record.target_observation_digest is None:
            failures.append(f"verification target '{target.id}' has no digest snapshot")
        elif target.digest != record.target_observation_digest:
            failures.append(f"verification target '{target.id}' digest changed since verification")
        elif not _file_matches(target, observation_files.get(target.id, Path("/nonexistent"))):
            failures.append(f"verification target '{target.id}' failed integrity")

    def closure(record_id: str) -> tuple[set[str], set[str]]:
        if record_id in active:
            failures.append(f"verification dependency cycle at '{record_id}'")
            return set(), set()
        record = records_by_id.get(record_id)
        if record is None:
            failures.append(f"verification parent '{record_id}' is absent")
            return set(), set()
        active.add(record_id)
        sources: set[str] = set()
        source_identities: set[str] = set()
        for basis in record.basis:
            if basis.observation_id == record.target_observation_id:
                failures.append("target observation cannot be a verification source")
                continue
            sources.add(basis.observation_id)
            marker = (basis.observation_id, basis.observation_digest)
            if marker in checked_sources:
                continue
            checked_sources.add(marker)
            observation = by_id.get(basis.observation_id)
            if observation is None:
                failures.append(f"verification source '{basis.observation_id}' is absent")
                continue
            source_identities.add(observation.source)
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
            parent_sources, parent_identities = closure(parent_id)
            sources.update(parent_sources)
            source_identities.update(parent_identities)
        active.remove(record_id)
        return sources, source_identities

    referenced_ids = {
        parent
        for record in requirement.verification_records
        for parent in record.parent_verification_ids
    }
    roots = [record for record in requirement.verification_records if record.verification_id not in referenced_ids]
    if not roots:
        failures.append("verification graph has no root record")
    elif requirement.observation_id is None:
        failures.append("structured verification graph has no requirement target")
    else:
        for root in roots:
            if root.target_observation_id != requirement.observation_id:
                failures.append(
                    f"verification root targets '{root.target_observation_id}' but requirement governs "
                    f"'{requirement.observation_id}'"
                )
    root_verifier_identities = {root.verifier_identity for root in roots}
    if roots and requirement.responsibility.verified_by not in root_verifier_identities:
        failures.append("verified_by must match a root structured verifier")
    root_sources = [closure(record.verification_id) for record in roots]
    for index, (first_ids, first_identities) in enumerate(root_sources):
        for second_ids, second_identities in root_sources[index + 1:]:
            shared = first_ids.intersection(second_ids)
            shared_identities = first_identities.intersection(second_identities)
            if shared:
                failures.append(
                    "independent verification roots share primary source(s): "
                    + ", ".join(sorted(shared))
                )
            if shared_identities:
                failures.append(
                    "independent verification roots share primary source identity(s): "
                    + ", ".join(sorted(shared_identities))
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
