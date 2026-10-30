"""Structured verification graph cases for source validity and independence."""

from datetime import timedelta

import pytest

from krakadyl.core.executor import execute_prepared_action, prepare_evidence_package, sha256_file
from krakadyl.core.verification import invalidate_observation, validate_verification_dependencies
from krakadyl.store import KrakadylStore
from krakadyl.core.models import (
    AuthorityVerdict,
    EvidenceRequirement,
    EvidenceCustody,
    Observation,
    TaskResponsibility,
    TaskStatus,
    VerificationBasis,
    VerificationRecord,
)
from test_invalidation import NOW, _action, _mandate  # noqa: F401


def _observation(tmp_path, observation_id, source, content):
    path = tmp_path / f"{observation_id}.bin"
    path.write_bytes(content)
    digest = sha256_file(path)
    return Observation(
        id=observation_id,
        source=source,
        digest=digest,
        captured_at=NOW - timedelta(hours=1),
        actor="investigator-A",
        evidence_custody=EvidenceCustody(
            acquired_by="investigator-A",
            acquired_at=NOW - timedelta(hours=1),
            acquisition_method="forensic-source-reader",
            integrity_digest=digest,
        ),
    ), path


def _requirement(target, first_source, second_source):
    return EvidenceRequirement(
        id="req-target",
        predicate="target observation is independently corroborated",
        acceptable_source_class="forensic source reader",
        observation_id=target.id,
        resolved=True,
        responsibility=TaskResponsibility(
            owner="investigator-A",
            status=TaskStatus.VERIFIED_DONE,
            reported_done_by="investigator-A",
            verified_by="investigator-C",
            verification_method="structured-peer-review",
            verified_against="legacy display only",
        ),
        verification_records=(
            VerificationRecord(
                verification_id="verification-one",
                verifier_identity="investigator-C",
                target_observation_id=target.id,
                basis=(VerificationBasis(
                    observation_id=first_source.id,
                    observation_digest=first_source.digest,
                ),),
                method="compare against primary source one",
                recorded_at=NOW,
            ),
            VerificationRecord(
                verification_id="verification-two",
                verifier_identity="investigator-D",
                target_observation_id=target.id,
                basis=(VerificationBasis(
                    observation_id=second_source.id,
                    observation_digest=second_source.digest,
                ),),
                method="compare against primary source two",
                recorded_at=NOW,
            ),
        ),
    )


def test_shared_primary_source_cannot_be_called_independent(graph_case):
    observations, _, _, target = graph_case
    primary = next(item for item in observations if item.id == "obs-primary-1")
    with pytest.raises(ValueError, match="share a primary source"):
        EvidenceRequirement(
            id="req-target",
            predicate="target observation is independently corroborated",
            acceptable_source_class="forensic source reader",
            observation_id=target.id,
            resolved=True,
            responsibility=TaskResponsibility(
                owner="investigator-A", status=TaskStatus.VERIFIED_DONE,
                reported_done_by="investigator-A", verified_by="investigator-C",
                verification_method="structured-peer-review",
            ),
            verification_records=tuple(
                VerificationRecord(
                    verification_id=f"verification-{index}",
                    verifier_identity=verifier,
                    target_observation_id=target.id,
                    basis=(VerificationBasis(
                        observation_id=primary.id, observation_digest=primary.digest,
                    ),),
                    method="same primary source",
                    recorded_at=NOW,
                )
                for index, verifier in enumerate(("investigator-C", "investigator-D"), start=1)
            ),
        )


def test_requirement_verifier_must_be_present_in_structured_records(graph_case):
    _, _, requirement, _ = graph_case
    mismatched = requirement.model_copy(update={
        "responsibility": requirement.responsibility.model_copy(update={
            "verified_by": "investigator-E",
        }),
    })

    with pytest.raises(ValueError, match="verified_by must match a root structured verifier"):
        EvidenceRequirement(**mismatched.model_dump())


def test_requirement_verifier_must_be_a_root_verifier(graph_case):
    observations, _, requirement, target = graph_case
    primary_one = next(item for item in observations if item.id == "obs-primary-1")
    primary_two = next(item for item in observations if item.id == "obs-primary-2")
    mismatched = requirement.model_copy(update={
        "responsibility": requirement.responsibility.model_copy(update={
            "verified_by": "investigator-E",
        }),
        "verification_records": (
            VerificationRecord(
                verification_id="parent-check",
                verifier_identity="investigator-E",
                target_observation_id=primary_one.id,
                basis=(VerificationBasis(
                    observation_id=primary_two.id, observation_digest=primary_two.digest,
                ),),
                method="check primary one",
                recorded_at=NOW,
            ),
            VerificationRecord(
                verification_id="root-check",
                verifier_identity="investigator-C",
                target_observation_id=target.id,
                basis=(VerificationBasis(
                    observation_id=primary_one.id, observation_digest=primary_one.digest,
                ),),
                parent_verification_ids=("parent-check",),
                method="check target",
                recorded_at=NOW,
            ),
        ),
    })

    with pytest.raises(ValueError, match="verified_by must match a root structured verifier"):
        EvidenceRequirement(**mismatched.model_dump())


def test_verification_cannot_use_target_as_its_own_primary_source(graph_case):
    observations, _, _, target = graph_case
    with pytest.raises(ValueError, match="target observation cannot be a verification source"):
        EvidenceRequirement(
            id="req-target",
            predicate="target observation is independently corroborated",
            acceptable_source_class="forensic source reader",
            observation_id=target.id,
            resolved=True,
            responsibility=TaskResponsibility(
                owner="investigator-A", status=TaskStatus.VERIFIED_DONE,
                reported_done_by="investigator-A", verified_by="investigator-C",
                verification_method="structured-peer-review",
            ),
            verification_records=(
                VerificationRecord(
                    verification_id="self-check",
                    verifier_identity="investigator-C",
                    target_observation_id=target.id,
                    basis=(VerificationBasis(
                        observation_id=target.id, observation_digest=target.digest,
                    ),),
                    method="re-read the target as its own source",
                    recorded_at=NOW,
                ),
            ),
        )


def test_verification_observation_dependencies_cannot_cycle(graph_case):
    observations, _, requirement, target = graph_case
    primary_one = next(item for item in observations if item.id == "obs-primary-1")
    cyclic = requirement.model_copy(update={
        "verification_records": (
            VerificationRecord(
                verification_id="check-primary-one",
                verifier_identity="investigator-B",
                target_observation_id=primary_one.id,
                basis=(VerificationBasis(
                    observation_id=target.id, observation_digest=target.digest,
                ),),
                method="check primary one against target",
                recorded_at=NOW,
            ),
            VerificationRecord(
                verification_id="root-check",
                verifier_identity="investigator-C",
                target_observation_id=target.id,
                basis=(VerificationBasis(
                    observation_id=primary_one.id, observation_digest=primary_one.digest,
                ),),
                parent_verification_ids=("check-primary-one",),
                method="check target through primary one",
                recorded_at=NOW,
            ),
        ),
    })

    with pytest.raises(ValueError, match="observation dependency graph contains a cycle"):
        EvidenceRequirement(**cyclic.model_dump())


def test_verification_record_target_must_exist(graph_case):
    observations, files, requirement, target = graph_case
    primary_one = next(item for item in observations if item.id == "obs-primary-1")
    dangling = requirement.model_copy(update={
        "verification_records": (
            VerificationRecord(
                verification_id="dangling-parent",
                verifier_identity="investigator-B",
                target_observation_id="obs-not-present",
                basis=(VerificationBasis(
                    observation_id=primary_one.id, observation_digest=primary_one.digest,
                ),),
                method="check missing target",
                recorded_at=NOW,
            ),
            VerificationRecord(
                verification_id="root-check",
                verifier_identity="investigator-C",
                target_observation_id=target.id,
                basis=(VerificationBasis(
                    observation_id=primary_one.id, observation_digest=primary_one.digest,
                ),),
                parent_verification_ids=("dangling-parent",),
                method="check target",
                recorded_at=NOW,
            ),
        ),
    })

    failures = validate_verification_dependencies(dangling, observations, files)

    assert any("verification target 'obs-not-present' is absent" in failure for failure in failures)


def test_verification_record_target_integrity_is_rechecked(graph_case):
    observations, files, requirement, target = graph_case
    primary_one = next(item for item in observations if item.id == "obs-primary-1")
    primary_two = next(item for item in observations if item.id == "obs-primary-2")
    recursive = requirement.model_copy(update={
        "verification_records": (
            VerificationRecord(
                verification_id="parent-check",
                verifier_identity="investigator-B",
                target_observation_id=primary_one.id,
                basis=(VerificationBasis(
                    observation_id=primary_two.id, observation_digest=primary_two.digest,
                ),),
                method="check primary one",
                recorded_at=NOW,
            ),
            VerificationRecord(
                verification_id="root-check",
                verifier_identity="investigator-C",
                target_observation_id=target.id,
                basis=(VerificationBasis(
                    observation_id=primary_two.id, observation_digest=primary_two.digest,
                ),),
                parent_verification_ids=("parent-check",),
                method="check target",
                recorded_at=NOW,
            ),
        ),
    })
    files[primary_one.id].write_bytes(b"primary one changed")

    failures = validate_verification_dependencies(recursive, observations, files)

    assert any("verification target 'obs-primary-1' failed integrity" in failure for failure in failures)


def test_verification_target_digest_must_match_custody_digest(graph_case):
    observations, files, requirement, target = graph_case
    drifted_target = target.model_copy(update={"digest": "f" * 64})
    drifted_observations = [
        drifted_target if observation.id == target.id else observation
        for observation in observations
    ]

    failures = validate_verification_dependencies(requirement, drifted_observations, files)

    assert any("verification target 'obs-target' failed integrity" in failure for failure in failures)


@pytest.fixture
def graph_case(tmp_path):
    target, target_path = _observation(tmp_path, "obs-target", "device-A", b"target bytes")
    primary_one, primary_one_path = _observation(tmp_path, "obs-primary-1", "primary-one", b"source one")
    primary_two, primary_two_path = _observation(tmp_path, "obs-primary-2", "primary-two", b"source two")
    observations = [target, primary_one, primary_two]
    files = {
        target.id: target_path,
        primary_one.id: primary_one_path,
        primary_two.id: primary_two_path,
    }
    return observations, files, _requirement(target, primary_one, primary_two), target


def test_invalidated_primary_source_blocks_execution_without_requirement_update(tmp_path, graph_case):
    observations, files, requirement, target = graph_case
    mandate = _mandate()

    decision, prepared = prepare_evidence_package(
        proposed_action=_action(), mandate=mandate,
        observations=observations, requirements=[requirement], observation_files=files,
        allowed_device="device-A", destination="reviewer-authorized", now=NOW,
    )
    assert decision.verdict == AuthorityVerdict.ALLOWED
    assert prepared is not None

    files["obs-primary-1"].write_bytes(b"primary source invalidated")
    receipt = execute_prepared_action(
        prepared=prepared, decision=decision, proposed_action=_action(),
        observations=observations, requirements=[requirement], observation_files=files,
        current_mandate=mandate, consumed_nonces=set(), out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=2),
    )

    assert receipt.executed is False
    assert "verification dependency graph invalid" in receipt.observed_effect
    assert not (tmp_path / "package" / "manifest.json").exists()


def test_logically_invalidated_primary_source_blocks_even_when_bytes_match(tmp_path, graph_case):
    observations, files, requirement, _ = graph_case
    mandate = _mandate()
    decision, prepared = prepare_evidence_package(
        proposed_action=_action(), mandate=mandate,
        observations=observations, requirements=[requirement], observation_files=files,
        allowed_device="device-A", destination="reviewer-authorized", now=NOW,
    )
    assert prepared is not None

    invalidated = [
        Observation(**{
            **observation.model_dump(),
            "invalidated": True,
            "invalidation_reason": "primary source was later shown to be contaminated",
        })
        if observation.id == "obs-primary-1" else observation
        for observation in observations
    ]
    receipt = execute_prepared_action(
        prepared=prepared, decision=decision, proposed_action=_action(),
        observations=invalidated, requirements=[requirement], observation_files=files,
        current_mandate=mandate, consumed_nonces=set(), out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=2),
    )

    assert receipt.executed is False
    assert "invalidated" in receipt.observed_effect


def test_recursive_shared_primary_source_is_not_independent(graph_case):
    observations, files, requirement, target = graph_case
    primary_one = next(item for item in observations if item.id == "obs-primary-1")
    primary_two = next(item for item in observations if item.id == "obs-primary-2")
    recursive = requirement.model_copy(update={
        "verification_records": (
            VerificationRecord(
                verification_id="parent-check",
                verifier_identity="investigator-B",
                target_observation_id=primary_one.id,
                basis=(VerificationBasis(
                    observation_id=primary_two.id, observation_digest=primary_two.digest,
                ),),
                method="check source one against source two",
                recorded_at=NOW,
            ),
            VerificationRecord(
                verification_id="root-one",
                verifier_identity="investigator-C",
                target_observation_id=target.id,
                basis=(VerificationBasis(
                    observation_id=primary_one.id, observation_digest=primary_one.digest,
                ),),
                parent_verification_ids=("parent-check",),
                method="review target through source one",
                recorded_at=NOW,
            ),
            VerificationRecord(
                verification_id="root-two",
                verifier_identity="investigator-D",
                target_observation_id=target.id,
                basis=(VerificationBasis(
                    observation_id=primary_two.id, observation_digest=primary_two.digest,
                ),),
                method="review target through source two",
                recorded_at=NOW,
            ),
        ),
    })

    failures = validate_verification_dependencies(recursive, observations, files)

    assert any("share primary source" in failure for failure in failures)


def test_observation_invalidation_is_atomic_and_visible_in_activity(tmp_path):
    observation, path = _observation(tmp_path, "obs-primary", "primary", b"primary bytes")
    store = KrakadylStore(tmp_path / "case.db")
    store.put("case-001", "observation", observation, NOW.isoformat())

    updated = invalidate_observation(
        store, case_id="case-001", observation_id=observation.id,
        actor_identity="investigator-C", reason="source provenance was disproved", now=NOW,
    )

    assert updated.invalidated is True
    assert updated.invalidation_reason == "source provenance was disproved"
    persisted = store.get("case-001", "observation", observation.id, Observation)
    assert persisted.invalidated is True
    assert any(event["kind"] == "observation_invalidated" for event in store.list_events("case-001"))
    assert path.read_bytes() == b"primary bytes"
    store.close()


def test_store_invalidation_blocks_a_prepared_action_after_reload(tmp_path, graph_case):
    observations, files, requirement, _ = graph_case
    store = KrakadylStore(tmp_path / "case.db")
    for observation in observations:
        store.put("case-001", "observation", observation, NOW.isoformat())
    mandate = _mandate()
    decision, prepared = prepare_evidence_package(
        proposed_action=_action(), mandate=mandate,
        observations=observations, requirements=[requirement], observation_files=files,
        allowed_device="device-A", destination="reviewer-authorized", now=NOW,
    )
    assert prepared is not None

    invalidate_observation(
        store, case_id="case-001", observation_id="obs-primary-1",
        actor_identity="investigator-C", reason="provider provenance was invalidated", now=NOW,
    )
    reloaded = store.list("case-001", "observation", Observation)
    receipt = execute_prepared_action(
        prepared=prepared, decision=decision, proposed_action=_action(),
        observations=reloaded, requirements=[requirement], observation_files=files,
        current_mandate=mandate, consumed_nonces=set(), out_dir=tmp_path / "package",
        now=NOW + timedelta(minutes=1),
    )

    assert receipt.executed is False
    assert "invalidated" in receipt.observed_effect
    assert not (tmp_path / "package" / "manifest.json").exists()
    store.close()
