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
    RecoveryWindow,
    RecoveryWindowKind,
    TaskResponsibility,
    TaskStatus,
)
from krakadyl.store import KrakadylStore

CASE_ID = "case-001"
# Seeded mandates stay valid long enough to demo through judging and
# beyond — found while wiring Level 3: the original +5 days expired them
# on 2026-11-01, before the 2026-11-04 deadline, which would have turned
# every live demo action into FORBIDDEN (correctly, but not usefully).
SEED_MANDATE_VALIDITY = timedelta(days=30)
CAPTURE_MANDATE_ID = "mandate-capture-001"
CLOCK_REQUIREMENT_ID = "req-device-a-clock"
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
        valid_until=SEED_NOW + SEED_MANDATE_VALIDITY,
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
    # Level 3: a separate, narrower mandate for capture — the package
    # export mandate above never grants acquiring anything new, and
    # widening it would silently change what every Level 1/2 check sees.
    capture_mandate = Mandate(
        id=CAPTURE_MANDATE_ID,
        issuer="legal-authority-001",
        principal="investigator-A",
        resources=[f"{CASE_ID}/operator-intake"],
        operations=["capture", "derive_annotation"],
        destinations=["local-only", "https://api.meta.ai/v1"],
        valid_from=SEED_NOW - timedelta(days=1),
        valid_until=SEED_NOW + SEED_MANDATE_VALIDITY,
    )
    requirements.append(
        EvidenceRequirement(
            id=CLOCK_REQUIREMENT_ID,
            predicate="device-A's clock offset against reference time is established",
            acceptable_source_class="operator photograph",
            recovery_window=RecoveryWindow(
                kind=RecoveryWindowKind.CONDITIONAL,
                condition="device-A's battery depletes or the device is powered off",
                what_is_lost_if_missed="the live clock state device-A had at seizure",
                depends_on_hypothesis_ids=["hyp-002"],
            ),
            responsibility=TaskResponsibility(owner="investigator-A", status=TaskStatus.ASSIGNED),
            discriminating_question=(
                "Photographed beside the reference clock, does device-A's on-screen clock "
                "match reference time within one minute?"
            ),
            answer_classes=["clock_matches_reference", "clock_offset_detected", "not_determinable"],
        )
    )
    hypotheses = [
        Hypothesis(
            id="hyp-001",
            explanation="Device A's photos were taken at the scene before device B arrived.",
            status=HypothesisStatus.ACCEPTED,
            discriminating_requirement_id="req-timestamp-check",
        ),
        Hypothesis(
            id="hyp-002",
            explanation=(
                "Device A's clock was correct at seizure, so its photo timestamps can be "
                "compared directly with device B's."
            ),
            status=HypothesisStatus.PROPOSED,
            discriminating_requirement_id=CLOCK_REQUIREMENT_ID,
        ),
    ]

    now_iso = SEED_NOW.isoformat()
    store.put(CASE_ID, "mission", mission, now_iso)
    store.put(CASE_ID, "mandate", mandate, now_iso)
    store.put(CASE_ID, "mandate", capture_mandate, now_iso)
    for o in observations:
        store.put(CASE_ID, "observation", o, now_iso)
    for r in requirements:
        store.put(CASE_ID, "requirement", r, now_iso)
    for h in hypotheses:
        store.put(CASE_ID, "hypothesis", h, now_iso)
    store.log_event(CASE_ID, "seeded", "Case seeded: two-device synthetic case", {}, now_iso)
