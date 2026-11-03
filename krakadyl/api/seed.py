"""Seeds the synthetic demo cases into the persistent store, on first use
only. `case-001` is the original two-device case the demos/tests walk
(ALLOWED). Three more cases make the other engine outcomes visible in the
workspace so a reviewer can see the deterministic engine say no, in three
distinct and honest ways:

  case-001        ALLOWED          evidence verified, authority granted
  case-gather     GATHER_EVIDENCE  a device-A capture is still open but
                                   an authorized source can still get it
  case-lost       FORBIDDEN        a device-A piece was reported done but
                                   never verified, and the source is gone
  case-scope      FORBIDDEN        the mandate authorizes partner-share,
                                   not the reviewer the action targets

All four are prepared by the UI with the same default action (device-A ->
reviewer-authorized), so only the seeded facts change the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
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

# The four demo cases, in the order the workspace selector lists them.
DEMO_CASES = ["case-001", "case-gather", "case-lost", "case-scope"]


def observation_file_path(data_dir: Path, case_id: str, obs_id: str) -> Path:
    return data_dir / case_id / "raw" / f"{obs_id}.jpg"


def _make_observation(
    data_dir: Path, case_id: str, obs_id: str, source: str, content: bytes
) -> Observation:
    path = observation_file_path(data_dir, case_id, obs_id)
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


def _claimed_requirement(req_id: str, predicate: str, observation_id: str) -> EvidenceRequirement:
    """Reported done by its owner, never independently verified, and no
    discriminating question — so nothing can route a new capture. Evidence
    reads as MISSING with no authorized source to resolve it."""
    return EvidenceRequirement(
        id=req_id,
        predicate=predicate,
        acceptable_source_class="forensic acquisition tool",
        observation_id=observation_id,
        resolved=False,
        responsibility=TaskResponsibility(
            owner="investigator-A",
            status=TaskStatus.REPORTED_DONE,
            reported_done_by="investigator-A",
        ),
    )


def _routable_requirement(req_id: str, observation_id: str) -> EvidenceRequirement:
    """Open, with a discriminating question and a conditional recovery
    window — an authorized operator photograph can still resolve it, so
    evidence reads as MISSING but resolvable (GATHER_EVIDENCE)."""
    return EvidenceRequirement(
        id=req_id,
        predicate="device-A's clock offset against reference time is established",
        acceptable_source_class="operator photograph",
        observation_id=observation_id,
        resolved=False,
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


def _capture_mandate(case_id: str) -> Mandate:
    # Level 3: a separate, narrower mandate for capture — the package
    # export mandate never grants acquiring anything new.
    return Mandate(
        id=CAPTURE_MANDATE_ID,
        issuer="legal-authority-001",
        principal="investigator-A",
        resources=[f"{case_id}/operator-intake"],
        operations=["capture", "derive_annotation"],
        destinations=["local-only", "https://api.meta.ai/v1"],
        valid_from=SEED_NOW - timedelta(days=1),
        valid_until=SEED_NOW + SEED_MANDATE_VALIDITY,
    )


@dataclass
class _CaseSpec:
    case_id: str
    objective: str
    destinations: list[str]
    # per-device-A-observation requirement kind: "verified" | "claimed" | "routable"
    a1_kind: str


_SPECS = {
    "case-001": _CaseSpec(
        case_id="case-001",
        objective="Prepare the device-A evidence package for the authorized reviewer.",
        destinations=["reviewer-authorized"],
        a1_kind="verified",
    ),
    "case-gather": _CaseSpec(
        case_id="case-gather",
        objective="Prepare the device-A package — a clock check on obs-a1 is still open.",
        destinations=["reviewer-authorized"],
        a1_kind="routable",
    ),
    "case-lost": _CaseSpec(
        case_id="case-lost",
        objective="Prepare the device-A package — obs-a1 was reported done but never verified.",
        destinations=["reviewer-authorized"],
        a1_kind="claimed",
    ),
    "case-scope": _CaseSpec(
        case_id="case-scope",
        objective="Prepare the device-A package — the mandate only authorizes partner-share.",
        destinations=["partner-share"],
        a1_kind="verified",
    ),
}


def _seed_one(store: KrakadylStore, data_dir: Path, spec: _CaseSpec) -> None:
    case_id = spec.case_id
    if store.case_exists(case_id):
        return

    observations = [
        _make_observation(data_dir, case_id, "obs-a1", "device-A", b"device A photo one, authentic bytes"),
        _make_observation(data_dir, case_id, "obs-a2", "device-A", b"device A photo two, authentic bytes"),
        _make_observation(data_dir, case_id, "obs-b1", "device-B", b"device B photo one - must stay excluded"),
    ]
    mandate = Mandate(
        # The API looks up the root mandate by the fixed id "mandate-001";
        # each case is its own namespace, so the id is shared across cases.
        id="mandate-001",
        issuer="legal-authority-001",
        principal="investigator-A",
        resources=[f"{case_id}/device-A"],
        operations=["package_export"],
        destinations=spec.destinations,
        valid_from=SEED_NOW - timedelta(days=1),
        valid_until=SEED_NOW + SEED_MANDATE_VALIDITY,
    )
    mission = Mission(
        id=case_id,
        objective=spec.objective,
        domain="forensic",
        mandate_id=mandate.id,
        termination_criteria="package delivered to reviewer-authorized, or closed as unresolved",
        created_at=SEED_NOW,
    )

    if spec.a1_kind == "verified":
        req_a1 = _verified_requirement("req-a1", "obs-a1 was acquired following the documented procedure", "obs-a1")
    elif spec.a1_kind == "claimed":
        req_a1 = _claimed_requirement("req-a1", "obs-a1 was acquired following the documented procedure", "obs-a1")
    else:  # routable: the package itself is blocked on an open, recoverable capture
        req_a1 = _routable_requirement("req-a1", "obs-a1")

    # The open clock requirement (governs no package observation) keeps the
    # Acquisition panel populated in every case, exactly as case-001 always had.
    clock_requirement = EvidenceRequirement(
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

    requirements = [
        req_a1,
        _verified_requirement("req-a2", "obs-a2 was acquired following the documented procedure", "obs-a2"),
        _verified_requirement("req-timestamp-check", "device-A and device-B timestamps are mutually consistent", None),
        clock_requirement,
    ]
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
    if spec.a1_kind == "routable":
        # Link a hypothesis to the blocked package requirement so an
        # authorized capture route exists for it (-> GATHER_EVIDENCE).
        hypotheses.append(
            Hypothesis(
                id="hyp-003",
                explanation="obs-a1's acquisition can be confirmed by an authorized operator photograph.",
                status=HypothesisStatus.PROPOSED,
                discriminating_requirement_id="req-a1",
            )
        )

    now_iso = SEED_NOW.isoformat()
    store.put(case_id, "mission", mission, now_iso)
    store.put(case_id, "mandate", mandate, now_iso)
    store.put(case_id, "mandate", _capture_mandate(case_id), now_iso)
    for o in observations:
        store.put(case_id, "observation", o, now_iso)
    for r in requirements:
        store.put(case_id, "requirement", r, now_iso)
    for h in hypotheses:
        store.put(case_id, "hypothesis", h, now_iso)
    store.log_event(case_id, "seeded", f"Case seeded: {case_id}", {}, now_iso)


def ensure_seeded(store: KrakadylStore, data_dir: Path) -> None:
    """Idempotent: seeds any of the demo cases that are not yet stored.
    Safe to call on every app startup."""
    for spec in _SPECS.values():
        _seed_one(store, data_dir, spec)
