#!/usr/bin/env python3
"""Runnable demo of the two-device synthetic case.

Four real runs against the real policy engine and executor — no mocked
decision, no simulated file I/O:

1. Happy path: package device A's evidence for the authorized reviewer.
2. Adversarial: try to package device B (outside the mandate) — FORBIDDEN.
3. Tampering: device A's file is modified after acquisition — FORBIDDEN,
   caught by the integrity check, not trusted.
4. The three-investigators scenario from the README, literally: the file
   is perfectly intact, but its acquisition was only REPORTED_DONE by
   investigator A — nobody independently verified it. FORBIDDEN, because
   a matching digest proves the file wasn't altered, not that the
   acquisition itself was ever checked.

Run: python demo/run_case_001.py
Output lands in ./out/case-001/ (gitignored).
"""

import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from krakadyl.core.executor import assemble_evidence_package, sha256_file
from krakadyl.core.models import (
    EvidenceCustody,
    EvidenceRequirement,
    Mandate,
    Observation,
    ProposedAction,
    TaskResponsibility,
    TaskStatus,
)

NOW = datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc)
OUT = Path(__file__).resolve().parent.parent / "out" / "case-001"


def make_observation(obs_id: str, source: str, path: Path, content: bytes) -> Observation:
    path.write_bytes(content)
    digest = sha256_file(path)
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


def verified_requirement(observation_id: str) -> EvidenceRequirement:
    """Independently verified: investigator C checked investigator A's
    acquisition, separate from the act of reporting it done."""
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
            verified_against="acquisition procedure followed, device matches case assignment",
        ),
    )


def unverified_requirement(observation_id: str) -> EvidenceRequirement:
    """The three-investigators scenario: A reports it done, nobody
    checks. REPORTED_DONE, not VERIFIED_DONE."""
    return EvidenceRequirement(
        id=f"req-{observation_id}",
        predicate=f"{observation_id} was acquired following the documented procedure",
        acceptable_source_class="forensic acquisition tool",
        observation_id=observation_id,
        responsibility=TaskResponsibility(
            owner="investigator-A",
            status=TaskStatus.REPORTED_DONE,
            reported_done_by="investigator-A",
        ),
    )


def mandate(**overrides) -> Mandate:
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


def action(action_id: str) -> ProposedAction:
    return ProposedAction(
        id=action_id,
        operation="package_export",
        arguments={"device": "device-A", "destination": "reviewer-authorized"},
        expected_effect="assemble a reviewer-ready package of device A's evidence only",
        mission_id="case-001",
    )


def report(title: str, decision, receipt) -> None:
    print(f"\n=== {title} ===")
    print(f"verdict:  {decision.verdict.value}")
    print(f"reasons:  {decision.reasons}")
    print(f"executed: {receipt.executed}")
    print(f"effect:   {receipt.observed_effect}")
    print(f"receipt hash: {receipt.hash}")


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    raw = OUT / "raw"
    raw.mkdir(parents=True)

    observations = [
        make_observation("obs-a1", "device-A", raw / "a1.jpg", b"device A photo one, authentic bytes"),
        make_observation("obs-a2", "device-A", raw / "a2.jpg", b"device A photo two, authentic bytes"),
        make_observation("obs-b1", "device-B", raw / "b1.jpg", b"device B photo one - must stay excluded"),
    ]
    files = {
        "obs-a1": raw / "a1.jpg",
        "obs-a2": raw / "a2.jpg",
        "obs-b1": raw / "b1.jpg",
    }
    requirements = [verified_requirement("obs-a1"), verified_requirement("obs-a2")]

    # 1. Happy path.
    decision1, receipt1 = assemble_evidence_package(
        proposed_action=action("action-001"),
        mandate=mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=OUT / "package",
        now=NOW,
    )
    report("1. Happy path — package device A for the authorized reviewer", decision1, receipt1)
    if receipt1.executed:
        manifest = (OUT / "package" / "manifest.json").read_text()
        print(f"manifest:\n{manifest}")

    # 2. Adversarial: try device B — outside the mandate.
    decision2, receipt2 = assemble_evidence_package(
        proposed_action=action("action-002"),
        mandate=mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-B",
        destination="reviewer-authorized",
        out_dir=OUT / "package-device-b-attempt",
        now=NOW,
        prev_receipt_hash=receipt1.hash,
    )
    report("2. Adversarial — device B is NOT in the mandate", decision2, receipt2)

    # 3. Tampering: device A's file changes after acquisition.
    files["obs-a1"].write_bytes(b"tampered content, does not match the acquired digest")
    decision3, receipt3 = assemble_evidence_package(
        proposed_action=action("action-003"),
        mandate=mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=OUT / "package-tampered-attempt",
        now=NOW,
        prev_receipt_hash=receipt2.hash,
    )
    report("3. Tampered file — integrity check must catch it", decision3, receipt3)

    # 4. The three-investigators scenario, literally: intact file, but
    # only REPORTED_DONE — nobody independently verified the acquisition.
    files["obs-a1"].write_bytes(b"device A photo one, authentic bytes")  # restore from #3
    unverified_requirements = [unverified_requirement("obs-a1"), verified_requirement("obs-a2")]
    decision4, receipt4 = assemble_evidence_package(
        proposed_action=action("action-004"),
        mandate=mandate(),
        observations=observations,
        requirements=unverified_requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        out_dir=OUT / "package-unverified-attempt",
        now=NOW,
        prev_receipt_hash=receipt3.hash,
    )
    report(
        "4. Reported done, never verified — the three-investigators scenario",
        decision4,
        receipt4,
    )

    print(f"\nAll output under: {OUT}")


if __name__ == "__main__":
    main()
