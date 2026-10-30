"""Validation of structured verification dependencies.

This is deliberately separate from the policy engine: it answers whether the
evidence basis is still valid, not whether the mandate permits the action.
Legacy requirements without structured records remain supported but do not
claim graph-level independence; callers can surface that limitation explicitly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from krakadyl.core.models import EvidenceRequirement, Observation


def _file_matches(observation: Observation, path: Path) -> bool:
    if not path.exists():
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
    failures: list[str] = []
    for record in requirement.verification_records:
        for basis in record.basis:
            observation = by_id.get(basis.observation_id)
            if observation is None:
                failures.append(f"verification source '{basis.observation_id}' is absent")
                continue
            if observation.digest != basis.observation_digest:
                failures.append(f"verification source '{basis.observation_id}' digest changed")
                continue
            if not _file_matches(observation, observation_files.get(observation.id, Path("/nonexistent"))):
                failures.append(f"verification source '{basis.observation_id}' failed integrity")
    return tuple(dict.fromkeys(failures))
