"""Level 2: the dependency-invalidation engine, exercised through the
real gap between preparing an action and executing it — something
changes in between, and execute_prepared_action() must catch it rather
than trust the ALLOWED verdict from prepare time.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from krakadyl.core.executor import (
    execute_prepared_action,
    prepare_evidence_package,
    sha256_file,
)
from krakadyl.core.invalidation import compute_combined_revision, staleness_reason
from krakadyl.core.models import (
    AuthorityVerdict,
    EvidenceCustody,
    EvidenceRequirement,
    Mandate,
    Observation,
    ProposedAction,
    TaskResponsibility,
    TaskStatus,
)

NOW = datetime(2026, 10, 27, 17, 0, tzinfo=timezone.utc)


def _observation(obs_id: str, source: str, file_path: Path, content: bytes) -> Observation:
    file_path.write_bytes(content)
    digest = sha256_file(file_path)
    return Observation(
        id=obs_id,
        source=source,
        digest=digest,
        captured_at=NOW - timedelta(hours=2),
        actor="investigator-A",
        evidence_custody=EvidenceCustody(
            acquired_by="investigator-A",
            acquired_at=NOW - timedelta(hours=2),
            acquisition_method="forensic-imaging-tool-v3",
            integrity_digest=digest,
        ),
    )


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
        revision="1",
    )
    defaults.update(overrides)
    return Mandate(**defaults)


def _verified_requirement(observation_id: str) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=f"req-{observation_id}",
        predicate=f"{observation_id} was acquired following the documented procedure",
        acceptable_source_class="forensic acquisition tool",
        observation_id=observation_id,
        resolved=True,
        responsibility=TaskResponsibility(
            owner="investigator-A",
            status=TaskStatus.VERIFIED_DONE,
            reported_done_by="investigator-A",
            verified_by="investigator-C",
            verification_method="peer-review",
            verified_against="acquisition procedure followed",
        ),
    )


def _action() -> ProposedAction:
    return ProposedAction(
        id="action-001",
        operation="package_export",
        arguments={"device": "device-A", "destination": "reviewer-authorized"},
        expected_effect="assemble a reviewer-ready package of device A's evidence only",
        mission_id="case-001",
    )


def test_staleness_reason_is_none_when_nothing_changed():
    digests = {"obs-a1": "d1", "obs-a2": "d2"}
    revision = compute_combined_revision(digests)
    assert (
        staleness_reason(
            source_revision_checked=revision,
            mandate_revision_checked="1",
            current_resource_digests=digests,
            current_mandate_revision="1",
        )
        is None
    )


def test_staleness_reason_names_mandate_change_first():
    digests = {"obs-a1": "d1"}
    revision = compute_combined_revision(digests)
    reason = staleness_reason(
        source_revision_checked=revision,
        mandate_revision_checked="1",
        current_resource_digests={"obs-a1": "DIFFERENT"},  # both changed
        current_mandate_revision="2",
    )
    assert "mandate" in reason


def test_prepared_action_executes_when_nothing_changed(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic device A photo")]
    files = {"obs-a1": raw / "a1.jpg"}
    mandate = _mandate()

    decision, prepared = prepare_evidence_package(
        proposed_action=_action(),
        mandate=mandate,
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )
    assert decision.verdict == AuthorityVerdict.ALLOWED
    assert prepared is not None

    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=_action(),
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        current_mandate=mandate,
        consumed_nonces=set(),
        out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=2),
    )
    assert receipt.executed is True


def test_invalidated_verification_dependency_blocks_execution(tmp_path):
    """A VERIFIED_DONE label is not enough after its independent basis is
    invalidated between preparation and execution."""
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic device A photo")]
    files = {"obs-a1": raw / "a1.jpg"}
    mandate = _mandate()
    verified = _verified_requirement("obs-a1")

    decision, prepared = prepare_evidence_package(
        proposed_action=_action(),
        mandate=mandate,
        observations=observations,
        requirements=[verified],
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )
    assert prepared is not None

    invalidated = EvidenceRequirement(**{
        **verified.model_dump(),
        "responsibility": TaskResponsibility(**{
            **verified.responsibility.model_dump(),
            "verified_against": "primary source invalidated after both independent checks",
        }),
    })
    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=_action(),
        observations=observations,
        requirements=[invalidated],
        observation_files=files,
        current_mandate=mandate,
        consumed_nonces=set(),
        out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=3),
    )

    assert receipt.executed is False
    assert "verification dependency" in receipt.observed_effect.lower()
    assert not (tmp_path / "package" / "manifest.json").exists()


def test_invalidated_target_observation_blocks_legacy_execution(tmp_path):
    """Logical invalidation must block the governed observation itself.

    This is the legacy variant: the requirement has no structured dependency
    records, so the invalidation cannot be discovered through a basis walk.
    The target observation state still must be honored at the execution sink.
    """
    raw = tmp_path / "raw"
    raw.mkdir()
    observation = _observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic device A photo")
    files = {observation.id: raw / "a1.jpg"}
    mandate = _mandate()
    requirement = _verified_requirement(observation.id)

    decision, prepared = prepare_evidence_package(
        proposed_action=_action(),
        mandate=mandate,
        observations=[observation],
        requirements=[requirement],
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )
    assert prepared is not None

    invalidated = observation.model_copy(update={
        "invalidated": True,
        "invalidation_reason": "the target source was later disproved",
    })
    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=_action(),
        observations=[invalidated],
        requirements=[requirement],
        observation_files=files,
        current_mandate=mandate,
        consumed_nonces=set(),
        out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=3),
    )

    assert receipt.executed is False
    assert "invalidated" in receipt.observed_effect.lower()
    assert not (tmp_path / "package" / "manifest.json").exists()


def test_duplicate_requirements_for_one_observation_are_not_last_write_wins(tmp_path):
    """One observation cannot inherit the most favorable duplicate requirement."""
    raw = tmp_path / "raw"
    raw.mkdir()
    observation = _observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic device A photo")
    files = {observation.id: raw / "a1.jpg"}
    mandate = _mandate()
    verified = _verified_requirement(observation.id)
    unverified = EvidenceRequirement(**{
        **verified.model_dump(),
        "id": "req-unverified",
        "resolved": False,
        "responsibility": TaskResponsibility(**{
            **verified.responsibility.model_dump(),
            "status": TaskStatus.REPORTED_DONE,
            "verified_by": None,
            "verification_method": None,
            "verified_against": None,
        }),
    })

    decision, prepared = prepare_evidence_package(
        proposed_action=_action(),
        mandate=mandate,
        observations=[observation],
        requirements=[unverified, verified],
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )

    assert decision.verdict != AuthorityVerdict.ALLOWED
    assert prepared is None


def test_prepared_action_without_dependency_snapshot_is_not_executable(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic device A photo")]
    files = {"obs-a1": raw / "a1.jpg"}
    mandate = _mandate()
    requirement = _verified_requirement("obs-a1")
    decision, prepared = prepare_evidence_package(
        proposed_action=_action(), mandate=mandate, observations=observations,
        requirements=[requirement], observation_files=files, allowed_device="device-A",
        destination="reviewer-authorized", now=NOW,
    )
    legacy_prepared = prepared.model_copy(update={"requirement_revisions": ()})

    receipt = execute_prepared_action(
        prepared=legacy_prepared, decision=decision, proposed_action=_action(),
        observations=observations, requirements=[requirement], observation_files=files,
        current_mandate=mandate, consumed_nonces=set(), out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=1),
    )

    assert receipt.executed is False
    assert "no verification dependency snapshot" in receipt.observed_effect


def test_mandate_revoked_between_prepare_and_execute_blocks_execution(tmp_path):
    """The exact Level 2 scenario: an action is prepared and ALLOWED,
    then the mandate is revoked before it runs. Execution must be
    blocked — the earlier ALLOWED verdict is not a standing permission.
    """
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic device A photo")]
    files = {"obs-a1": raw / "a1.jpg"}
    mandate_at_prepare = _mandate(revision="1")

    decision, prepared = prepare_evidence_package(
        proposed_action=_action(),
        mandate=mandate_at_prepare,
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )
    assert prepared is not None

    # The mandate gets revoked in the gap — represented as a new,
    # bumped-revision Mandate object (mandates are immutable snapshots).
    mandate_now = _mandate(revision="2", revoked=True, revoked_reason="case reassigned to another unit")

    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=_action(),
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        current_mandate=mandate_now,
        consumed_nonces=set(),
        out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=5),
    )

    assert receipt.executed is False
    assert "mandate no longer grants this action" in receipt.observed_effect
    assert "revoked" in receipt.observed_effect
    assert not (tmp_path / "package" / "manifest.json").exists()


def test_source_file_changed_between_prepare_and_execute_blocks_execution(tmp_path):
    """The other Level 2 scenario: the file is fine at prepare time, but
    gets modified — tampered or legitimately re-acquired — before
    execute runs. Caught by recomputing the digest, not trusted from
    the prepare-time snapshot.
    """
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic device A photo")]
    files = {"obs-a1": raw / "a1.jpg"}
    mandate = _mandate()

    decision, prepared = prepare_evidence_package(
        proposed_action=_action(),
        mandate=mandate,
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )
    assert prepared is not None

    files["obs-a1"].write_bytes(b"content changed after prepare, before execute")

    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=_action(),
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        current_mandate=mandate,
        consumed_nonces=set(),
        out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=3),
    )

    assert receipt.executed is False
    assert "evidence no longer sufficient" in receipt.observed_effect
    assert "integrity check failed" in receipt.observed_effect


def test_expired_prepared_action_blocks_execution_even_if_nothing_else_changed(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic device A photo")]
    files = {"obs-a1": raw / "a1.jpg"}
    mandate = _mandate()

    decision, prepared = prepare_evidence_package(
        proposed_action=_action(),
        mandate=mandate,
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
        ttl=timedelta(minutes=5),
    )
    assert prepared is not None

    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=_action(),
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        current_mandate=mandate,
        consumed_nonces=set(),
        out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=10),  # past the 5-minute TTL
    )

    assert receipt.executed is False
    assert "expired" in receipt.observed_effect


def test_source_file_deleted_between_prepare_and_execute_is_caught(tmp_path):
    """A missing file must register as changed, not crash and not be
    silently skipped as if it were never part of the package."""
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic device A photo")]
    files = {"obs-a1": raw / "a1.jpg"}
    mandate = _mandate()

    decision, prepared = prepare_evidence_package(
        proposed_action=_action(),
        mandate=mandate,
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )
    assert prepared is not None

    files["obs-a1"].unlink()

    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=_action(),
        observations=observations,
        requirements=[_verified_requirement("obs-a1")],
        observation_files=files,
        current_mandate=mandate,
        consumed_nonces=set(),
        out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=2),
    )

    assert receipt.executed is False
    assert "evidence no longer sufficient" in receipt.observed_effect
    assert "integrity check failed" in receipt.observed_effect
