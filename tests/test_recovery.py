"""Level 2's other half: propose_recovery_route — when a specific piece
of evidence is the problem, retry with exactly that resource excluded,
through the same unmodified decision pipeline, instead of only blocking.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from krakadyl.core.executor import propose_recovery_route, sha256_file
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

NOW = datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc)


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
    )
    defaults.update(overrides)
    return Mandate(**defaults)


def _verified_requirement(req_id: str, observation_id: str) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
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
            verified_against="acquisition procedure followed, device matches case assignment",
        ),
    )


def _unverified_requirement(req_id: str, observation_id: str) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        predicate=f"{observation_id} was acquired following the documented procedure",
        acceptable_source_class="forensic acquisition tool",
        observation_id=observation_id,
        responsibility=TaskResponsibility(
            owner="investigator-A",
            status=TaskStatus.REPORTED_DONE,
            reported_done_by="investigator-A",
        ),
    )


def _proposed_action() -> ProposedAction:
    return ProposedAction(
        id="action-001",
        operation="package_export",
        arguments={"device": "device-A", "destination": "reviewer-authorized"},
        expected_effect="assemble a reviewer-ready package of device A's evidence only",
        mission_id="case-001",
    )


def test_recovers_a_package_excluding_the_tampered_file(tmp_path):
    """The literal README scenario: a package without the compromised
    attachment, not a package that includes it anyway, and not a flat
    refusal when a legitimate subset still exists.
    """
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [
        _observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic photo one"),
        _observation("obs-a2", "device-A", raw / "a2.jpg", b"authentic photo two"),
    ]
    files = {"obs-a1": raw / "a1.jpg", "obs-a2": raw / "a2.jpg"}
    requirements = [
        _verified_requirement("req-a1", "obs-a1"),
        _verified_requirement("req-a2", "obs-a2"),
    ]

    # obs-a1 is tampered after acquisition.
    files["obs-a1"].write_bytes(b"tampered content, does not match the acquired digest")

    outcome = propose_recovery_route(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )

    assert outcome.attempted is True
    assert outcome.excluded_resources == ["obs-a1"]
    assert outcome.closed_reason is None
    assert outcome.recovered_decision.verdict == AuthorityVerdict.ALLOWED
    assert outcome.recovered_prepared is not None
    assert outcome.recovered_prepared.resources_touched == ("obs-a2",)


def test_recovers_excluding_an_unverified_observation(tmp_path):
    """Same mechanism, different failure: a file that's intact but whose
    acquisition was never independently verified (REPORTED_DONE, not
    VERIFIED_DONE) — excluded the same way a tampered file would be.
    """
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [
        _observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic photo one"),
        _observation("obs-a2", "device-A", raw / "a2.jpg", b"authentic photo two"),
    ]
    files = {"obs-a1": raw / "a1.jpg", "obs-a2": raw / "a2.jpg"}
    requirements = [
        _unverified_requirement("req-a1", "obs-a1"),
        _verified_requirement("req-a2", "obs-a2"),
    ]

    outcome = propose_recovery_route(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )

    assert outcome.attempted is True
    assert outcome.excluded_resources == ["obs-a1"]
    assert outcome.recovered_prepared is not None
    assert outcome.recovered_prepared.resources_touched == ("obs-a2",)


def test_closes_honestly_when_nothing_legitimate_remains(tmp_path):
    """Only one observation exists, and it's the one that's compromised
    — excluding it leaves nothing to package. This must close honestly,
    never fabricate a package out of nothing to avoid saying so.
    """
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic photo one")]
    files = {"obs-a1": raw / "a1.jpg"}
    requirements = [_verified_requirement("req-a1", "obs-a1")]

    files["obs-a1"].write_bytes(b"tampered content")

    outcome = propose_recovery_route(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )

    assert outcome.attempted is True
    assert outcome.excluded_resources == ["obs-a1"]
    assert outcome.recovered_prepared is None
    assert outcome.closed_reason is not None
    assert "does not produce a legitimate route" in outcome.closed_reason


def test_does_not_attempt_recovery_for_a_revoked_mandate():
    """A missing permission is not a resource problem — excluding a file
    cannot restore authority. Recovery must not even try, and must say
    why, rather than silently returning an empty non-route.
    """
    outcome = propose_recovery_route(
        proposed_action=_proposed_action(),
        mandate=_mandate(revision="2", revoked=True, revoked_reason="case reassigned"),
        observations=[],
        requirements=[],
        observation_files={},
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )

    assert outcome.attempted is False
    assert outcome.recovered_prepared is None
    assert "no exclusion can" in outcome.closed_reason


def test_does_not_attempt_recovery_when_nothing_is_actually_failing(tmp_path):
    """If evidence is already sufficient, there is no failing resource to
    exclude — recovery is simply not applicable, not a no-op success.
    """
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [_observation("obs-a1", "device-A", raw / "a1.jpg", b"authentic photo one")]
    files = {"obs-a1": raw / "a1.jpg"}
    requirements = [_verified_requirement("req-a1", "obs-a1")]

    outcome = propose_recovery_route(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )

    assert outcome.attempted is False
    assert outcome.recovered_prepared is None
    assert "does not apply" in outcome.closed_reason
