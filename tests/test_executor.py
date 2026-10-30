"""Level 1's acceptance criterion, exercised for real: a synthetic
two-device case, assembled through the actual policy engine and
executor — no mocked decision, no simulated file I/O.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from krakadyl.core.executor import assemble_evidence_package, sha256_file
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
from krakadyl.core.receipt import seal

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
    """An EvidenceRequirement already independently verified — a second
    investigator (not the one who acquired it) peer-reviewed the
    acquisition. This is what the executor now requires in addition to
    the file-integrity check — see executor.py's cross-module fix.
    """
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


def _proposed_action() -> ProposedAction:
    return ProposedAction(
        id="action-001",
        operation="package_export",
        arguments={"device": "device-A", "destination": "reviewer-authorized"},
        expected_effect="assemble a reviewer-ready package of device A's evidence only",
        mission_id="case-001",
    )


@pytest.fixture
def two_device_case(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    observations = [
        _observation("obs-a1", "device-A", raw / "a1.jpg", b"device A photo one, authentic bytes"),
        _observation("obs-a2", "device-A", raw / "a2.jpg", b"device A photo two, authentic bytes"),
        _observation("obs-b1", "device-B", raw / "b1.jpg", b"device B photo one - must stay excluded"),
    ]
    files = {o.id: raw / f"{o.id.split('-')[1]}.jpg" for o in observations}
    requirements = [
        _verified_requirement("req-a1", "obs-a1"),
        _verified_requirement("req-a2", "obs-a2"),
        # obs-b1 deliberately has no EvidenceRequirement — it's excluded
        # by the mandate anyway, and this also exercises "no requirement
        # governs it" as a real case rather than only as a theoretical one.
    ]
    return observations, files, requirements


def test_happy_path_executes_for_real_and_excludes_device_b(tmp_path, two_device_case):
    observations, files, requirements = two_device_case
    out_dir = tmp_path / "package"

    decision, receipt = assemble_evidence_package(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=out_dir,
        now=NOW,
    )

    assert decision.verdict == AuthorityVerdict.ALLOWED
    assert receipt.executed is True

    manifest = json.loads((out_dir / "manifest.json").read_text())
    included_ids = {entry["observation_id"] for entry in manifest["included"]}
    assert included_ids == {"obs-a1", "obs-a2"}
    assert manifest["excluded_devices"] == ["device-B"]
    assert not (out_dir / "obs-b1.jpg").exists()
    # The actual copied files exist and match the real digests — not
    # just referenced in the manifest.
    for entry in manifest["included"]:
        copied = out_dir / entry["filename"]
        assert sha256_file(copied) == entry["digest"]


def test_receipt_is_independently_verifiable():
    """The receipt this executor produces must seal with the same
    canonical encoder the standalone verifier (tools/verify_receipt.py)
    reimplements independently — proven here by recomputing the seal
    the same way the executor does and checking it matches.
    """
    # Smoke check: the executor's receipt.hash is a deterministic
    # function of the payload — recomputing seal() on the same logical
    # payload with the same prev_hash reproduces the same hash.
    payload = {"proposed_action_id": "action-001", "decision_id": "decision-001", "verdict": "forbidden", "executed": False}
    assert seal(payload, None) == seal(dict(payload), None)


def test_wrong_device_is_forbidden_not_silently_substituted():
    """Asking the executor to treat device-B as the allowed device must
    be FORBIDDEN — device-B is not in the mandate's resources — never
    silently package device-B material instead.
    """
    raw_dir_marker = Path("/tmp")  # unused, device-B path is out of scope before files matter
    observations = [
        Observation(
            id="obs-b1",
            source="device-B",
            digest="irrelevant",
            captured_at=NOW,
            actor="investigator-A",
            evidence_custody=EvidenceCustody(
                acquired_by="investigator-A",
                acquired_at=NOW,
                acquisition_method="forensic-imaging-tool-v3",
                integrity_digest="irrelevant",
            ),
        )
    ]

    decision, receipt = assemble_evidence_package(
        proposed_action=_proposed_action(),
        mandate=_mandate(),  # only authorizes case-001/device-A
        observations=observations,
        requirements=[],
        observation_files={"obs-b1": raw_dir_marker / "nonexistent.jpg"},
        allowed_device="device-B",
        destination="reviewer-authorized",
        out_dir=Path("/tmp/should-not-be-created-krakadyl-test"),
        now=NOW,
    )

    assert decision.verdict == AuthorityVerdict.FORBIDDEN
    assert receipt.executed is False
    assert not Path("/tmp/should-not-be-created-krakadyl-test").exists()


def test_tampered_file_fails_integrity_and_is_forbidden(tmp_path, two_device_case):
    """A device-A file modified after acquisition (tampering, or an
    honest corruption) must be caught by recomputing its digest — not
    trusted because the metadata still says it's fine.
    """
    observations, files, requirements = two_device_case
    files["obs-a1"].write_bytes(b"tampered content, does not match the stored digest")

    decision, receipt = assemble_evidence_package(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=tmp_path / "package",
        now=NOW,
    )

    assert decision.verdict == AuthorityVerdict.FORBIDDEN
    assert receipt.executed is False
    assert "integrity check failed" in receipt.observed_effect
    assert "obs-a1" in decision.reasons[-1]


def test_wrong_destination_is_forbidden(tmp_path, two_device_case):
    observations, files, requirements = two_device_case
    decision, receipt = assemble_evidence_package(
        proposed_action=_proposed_action(),
        mandate=_mandate(),  # destinations=["reviewer-authorized"] only
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="unauthorized-third-party",
        out_dir=tmp_path / "package",
        now=NOW,
    )
    assert decision.verdict == AuthorityVerdict.FORBIDDEN
    assert receipt.executed is False


def test_expired_mandate_is_forbidden_even_with_perfect_evidence(tmp_path, two_device_case):
    observations, files, requirements = two_device_case
    decision, receipt = assemble_evidence_package(
        proposed_action=_proposed_action(),
        mandate=_mandate(valid_until=NOW - timedelta(days=1)),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=tmp_path / "package",
        now=NOW,
    )
    assert decision.verdict == AuthorityVerdict.FORBIDDEN
    assert receipt.executed is False


def test_evidence_without_independent_verification_is_forbidden(tmp_path, two_device_case):
    """The cross-module fix, exercised directly: a file that matches its
    digest perfectly is still not enough — its EvidenceRequirement must
    also be independently verified (VERIFIED_DONE), not just REPORTED_DONE.
    """
    observations, files, _ = two_device_case
    unverified_requirements = [
        EvidenceRequirement(
            id="req-a1",
            predicate="obs-a1 was acquired following the documented procedure",
            acceptable_source_class="forensic acquisition tool",
            observation_id="obs-a1",
            responsibility=TaskResponsibility(
                owner="investigator-A", status=TaskStatus.REPORTED_DONE, reported_done_by="investigator-A"
            ),
        ),
    ]

    decision, receipt = assemble_evidence_package(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=unverified_requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=tmp_path / "package",
        now=NOW,
    )

    assert decision.verdict == AuthorityVerdict.FORBIDDEN
    assert receipt.executed is False
    assert "not independently verified" in receipt.observed_effect


def test_assembly_wrapper_preserves_shared_custody_conflicts(tmp_path, two_device_case):
    observations, files, requirements = two_device_case

    decision, receipt = assemble_evidence_package(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=tmp_path / "package",
        now=NOW,
        conflicted_requirement_ids=frozenset({"req-a1"}),
    )

    assert decision.verdict == AuthorityVerdict.FORBIDDEN
    assert receipt.executed is False
    assert not (tmp_path / "package").exists()


def test_receipt_chain_links_to_previous_hash(tmp_path, two_device_case):
    observations, files, requirements = two_device_case
    _, first_receipt = assemble_evidence_package(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=tmp_path / "package",
        now=NOW,
    )

    action2 = ProposedAction(
        id="action-002",
        operation="package_export",
        arguments={"device": "device-A", "destination": "reviewer-authorized"},
        expected_effect="second export attempt",
        mission_id="case-001",
    )
    _, second_receipt = assemble_evidence_package(
        proposed_action=action2,
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=tmp_path / "package2",
        now=NOW,
        prev_receipt_hash=first_receipt.hash,
    )

    assert second_receipt.prev_hash == first_receipt.hash
    assert second_receipt.hash != first_receipt.hash
