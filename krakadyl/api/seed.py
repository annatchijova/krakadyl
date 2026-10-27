"""Seeds the two-device synthetic case this project's demos already
use, into the persistent store, on first use only. The same facts as
`demo/run_case_001.py` and `demo/run_case_002_level2.py` — this is the
case the frontend walks, not a separate fictional one.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from krakadyl.core.executor import sha256_file
from krakadyl.core.models import (
    EvidenceCustody,
    EvidenceRequirement,
    Hypothesis,
    HypothesisStatus,
    Mandate,
    Mission,
    Observation,
    TaskResponsibility,
    TaskStatus,
)
from krakadyl.store import KrakadylStore

CASE_ID = "case-001"
SEED_NOW = datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc)


def observation_file_path(data_dir: Path, case_id: str, obs_id: str) -> Path:
    return data_dir / case_id / "raw" / f"{obs_id}.jpg"


def _make_observation(data_dir: Path, obs_id: str, source: str, content: bytes) -> Observation:
    path = observation_file_path(data_dir, CASE_ID, obs_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    digest = sha256_file(path)
    return Observation(
        id=obs_id,
        source=source,
        digest=digest,
        captured_at=SEED_NOW - timedelta(hours=2),
        actor="investigator-A",
        evidence_custody=EvidenceCustody(
            acquired_by="investigator-A",
            acquired_at=SEED_NOW - timedelta(hours=2),
            acquisition_method="forensic-imaging-tool-v3",
            integrity_digest=digest,
        ),
    )


def _verified_requirement(req_id: str, predicate: str, observation_id: str | None) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        predicate=predicate,
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


def ensure_seeded(store: KrakadylStore, data_dir: Path) -> None:
    """Idempotent: does nothing if the case already has any stored
    object. Safe to call on every app startup.
    """
    if store.case_exists(CASE_ID):
        return

    observations = [
        _make_observation(data_dir, "obs-a1", "device-A", b"device A photo one, authentic bytes"),
        _make_observation(data_dir, "obs-a2", "device-A", b"device A photo two, authentic bytes"),
        _make_observation(data_dir, "obs-b1", "device-B", b"device B photo one - must stay excluded"),
    ]
    mandate = Mandate(
        id="mandate-001",
        issuer="legal-authority-001",
        principal="investigator-A",
        resources=["case-001/device-A"],
        operations=["package_export"],
        destinations=["reviewer-authorized"],
        valid_from=SEED_NOW - timedelta(days=1),
        valid_until=SEED_NOW + timedelta(days=5),
    )
    mission = Mission(
        id=CASE_ID,
        objective="Prepare the device-A evidence package for the authorized reviewer.",
        domain="forensic",
        mandate_id=mandate.id,
        termination_criteria="package delivered to reviewer-authorized, or closed as unresolved",
        created_at=SEED_NOW,
    )
    requirements = [
        _verified_requirement("req-a1", "obs-a1 was acquired following the documented procedure", "obs-a1"),
        _verified_requirement("req-a2", "obs-a2 was acquired following the documented procedure", "obs-a2"),
        _verified_requirement(
            "req-timestamp-check", "device-A and device-B timestamps are mutually consistent", None
        ),
    ]
    hypotheses = [
        Hypothesis(
            id="hyp-001",
            explanation="Device A's photos were taken at the scene before device B arrived.",
            status=HypothesisStatus.ACCEPTED,
            discriminating_requirement_id="req-timestamp-check",
        ),
    ]

    now_iso = SEED_NOW.isoformat()
    store.put(CASE_ID, "mission", mission, now_iso)
    store.put(CASE_ID, "mandate", mandate, now_iso)
    for o in observations:
        store.put(CASE_ID, "observation", o, now_iso)
    for r in requirements:
        store.put(CASE_ID, "requirement", r, now_iso)
    for h in hypotheses:
        store.put(CASE_ID, "hypothesis", h, now_iso)
    store.log_event(CASE_ID, "seeded", "Case seeded: two-device synthetic case", {}, now_iso)
