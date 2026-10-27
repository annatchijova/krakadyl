"""The real domain action: assembling a verifiable local evidence package.

Two phases, not one, as of the Level 2 build: `prepare_evidence_package`
resolves authority and evidence integrity and produces a `PreparedAction`
snapshot (Decision made, nothing executed yet); `execute_prepared_action`
revalidates that snapshot against the CURRENT mandate and resource state
immediately before acting — per the architecture's own rule that the
executor never just trusts a decision made earlier. Between the two
calls, real time can pass: a mandate can be revised or revoked, a file
can change. `assemble_evidence_package` is a thin convenience wrapper
calling both back to back, for callers that don't need the gap.

The flow, every time, no shortcuts: resolve authority via the mandate
(never trust the caller's claim of what device is "allowed"), verify
every included observation's integrity against the real file on disk
(never trust a stored digest without recomputing it), call decide()
for the verdict, and only execute if the verdict is ALLOWED *and* the
prepared snapshot is still current at execution time.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from krakadyl.core.continuity import evidence_state_from_requirement
from krakadyl.core.invalidation import compute_combined_revision, staleness_reason
from krakadyl.core.models import (
    AuthorityState,
    AuthorityVerdict,
    Decision,
    EvidenceRequirement,
    EvidenceState,
    Mandate,
    Observation,
    PreparedAction,
    ProposedAction,
    Receipt,
)
from krakadyl.core.policy import decide
from krakadyl.core.receipt import seal

DEFAULT_PREPARED_ACTION_TTL = timedelta(minutes=15)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_observation_integrity(observation: Observation, file_path: Path) -> bool:
    """Recomputes the digest from the actual file on disk. Never trusts
    the stored `integrity_digest` without checking it against real
    bytes — a tampered or substituted file must be caught here, not
    assumed away because the metadata says it's fine.
    """
    if not file_path.exists():
        return False
    return sha256_file(file_path) == observation.evidence_custody.integrity_digest


@dataclass
class MandateCheck:
    outside_scope: bool
    authority_state: AuthorityState
    reasons: list[str]


def check_mandate(
    mandate: Mandate,
    *,
    resource: str,
    operation: str,
    destination: str,
    now: datetime,
) -> MandateCheck:
    """The only place a (resource, operation, destination) triple gets
    checked against a Mandate. Nothing downstream re-derives this.
    """
    if mandate.revoked:
        return MandateCheck(
            outside_scope=True,
            authority_state=AuthorityState.DENIED,
            reasons=[f"mandate revoked: {mandate.revoked_reason}"],
        )
    if mandate.valid_until and now > mandate.valid_until:
        return MandateCheck(
            outside_scope=False,
            authority_state=AuthorityState.EXPIRED,
            reasons=["mandate validity window has closed"],
        )
    missing = []
    if resource not in mandate.resources:
        missing.append(f"resource '{resource}'")
    if operation not in mandate.operations:
        missing.append(f"operation '{operation}'")
    if destination not in mandate.destinations:
        missing.append(f"destination '{destination}'")
    if missing:
        return MandateCheck(
            outside_scope=True,
            authority_state=AuthorityState.DENIED,
            reasons=[f"outside mandate scope: {', '.join(missing)} not granted"],
        )
    return MandateCheck(
        outside_scope=False,
        authority_state=AuthorityState.GRANTED,
        reasons=["resource, operation, and destination are all within mandate scope"],
    )


def _not_executed_receipt(
    *, proposed_action: ProposedAction, decision: Decision, reasons: list[str], now: datetime, prev_hash: Optional[str]
) -> Receipt:
    payload = {
        "proposed_action_id": proposed_action.id,
        "decision_id": decision.id,
        "verdict": decision.verdict.value,
        "executed": False,
    }
    effect = "not executed: " + "; ".join(reasons)
    return Receipt(
        id=f"receipt-{proposed_action.id}",
        proposed_action_id=proposed_action.id,
        decision_id=decision.id,
        executed=False,
        observed_effect=effect,
        prev_hash=prev_hash,
        hash=seal(payload, prev_hash),
        created_at=now,
    )


def prepare_evidence_package(
    *,
    proposed_action: ProposedAction,
    mandate: Mandate,
    observations: list[Observation],
    requirements: list[EvidenceRequirement],
    observation_files: dict[str, Path],
    allowed_device: str,
    destination: str,
    now: datetime,
    ttl: timedelta = DEFAULT_PREPARED_ACTION_TTL,
) -> tuple[Decision, Optional[PreparedAction]]:
    """Resolves authority and evidence state for real. Returns a
    Decision always; returns a PreparedAction only when the verdict is
    ALLOWED — nothing is executed here, this only decides and snapshots.

    Evidence is sufficient only when BOTH hold, for every included
    observation: its `EvidenceRequirement` has independently reached
    `VERIFIED_DONE` (via `continuity.evidence_state_from_requirement` —
    the one place that decides, reused here rather than re-derived), and
    its file's digest still matches what was acquired. Neither check
    substitutes for the other: digest-matching proves the file wasn't
    altered since acquisition, not that the acquisition itself was
    verified; VERIFIED_DONE proves acquisition was verified, not that
    the file wasn't swapped afterward. Fixed 2026-10-27 — the executor
    used to only check the digest, never custody, per the cross-module
    red-team finding in docs/levels.md.
    """
    resource = f"{proposed_action.mission_id}/{allowed_device}"
    check = check_mandate(
        mandate,
        resource=resource,
        operation=proposed_action.operation,
        destination=destination,
        now=now,
    )

    included = [o for o in observations if o.source == allowed_device]
    excluded_devices = sorted({o.source for o in observations if o.source != allowed_device})

    requirements_by_observation = {r.observation_id: r for r in requirements if r.observation_id}

    integrity_failures = [
        o.id for o in included if not verify_observation_integrity(o, observation_files[o.id])
    ]

    unverified: list[str] = []
    for o in included:
        req = requirements_by_observation.get(o.id)
        if req is None:
            unverified.append(f"{o.id} (no EvidenceRequirement governs its acquisition)")
        elif evidence_state_from_requirement(req) != EvidenceState.SUFFICIENT:
            unverified.append(f"{o.id} (requirement '{req.id}' is {req.responsibility.status.value}, not independently verified)")

    if integrity_failures:
        evidence_state = EvidenceState.CONFLICTING
    elif not included:
        evidence_state = EvidenceState.MISSING
    elif unverified:
        evidence_state = EvidenceState.MISSING
    else:
        evidence_state = EvidenceState.SUFFICIENT

    verdict, policy_reasons = decide(
        evidence_state=evidence_state,
        authority_state=check.authority_state,
        outside_mandate_scope=check.outside_scope,
        resolvable_by_authorized_source=False,  # no re-acquisition path modeled yet (Level 3)
    )
    reasons = check.reasons + policy_reasons
    if integrity_failures:
        reasons.append(f"integrity check failed for: {', '.join(integrity_failures)}")
    if unverified:
        reasons.append(f"not independently verified: {', '.join(unverified)}")

    decision = Decision(
        id=f"decision-{proposed_action.id}",
        proposed_action_id=proposed_action.id,
        verdict=verdict,
        evidence_state=evidence_state,
        authority_state=check.authority_state,
        reasons=reasons,
        decided_at=now,
    )

    if verdict != AuthorityVerdict.ALLOWED:
        return decision, None

    resource_digests = {o.id: o.evidence_custody.integrity_digest for o in included}
    combined_revision = compute_combined_revision(resource_digests)
    prepared = PreparedAction(
        id=f"prepared-{proposed_action.id}",
        proposed_action_id=proposed_action.id,
        payload_digest=combined_revision,
        destination=destination,
        resources_touched=[o.id for o in included],
        excluded_sources=excluded_devices,
        source_revision_checked=combined_revision,
        mandate_revision_checked=mandate.revision,
        expires_at=now + ttl,
        nonce=secrets.token_hex(8),
    )
    return decision, prepared


def execute_prepared_action(
    *,
    prepared: PreparedAction,
    decision: Decision,
    proposed_action: ProposedAction,
    observations: list[Observation],
    observation_files: dict[str, Path],
    current_mandate: Mandate,
    out_dir: Path,
    now: datetime,
    prev_receipt_hash: Optional[str] = None,
) -> Receipt:
    """Revalidates the snapshot against the CURRENT mandate and current
    file state before doing anything — this is the one place a stale
    PreparedAction gets caught, never silently executed because it was
    ALLOWED at prepare time.
    """
    if now > prepared.expires_at:
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=[f"PreparedAction expired at {prepared.expires_at.isoformat()}"],
            now=now,
            prev_hash=prev_receipt_hash,
        )

    by_id = {o.id: o for o in observations}
    current_digests: dict[str, str] = {}
    for obs_id in prepared.resources_touched:
        if obs_id not in by_id:
            # Found by self-red-teaming: the Observation itself could be
            # absent from whatever list the caller passes to execute,
            # independent of whether its file still exists. Treat as
            # changed rather than crash on by_id[obs_id] later — an
            # inconsistency here is exactly the kind of thing staleness
            # must catch, not assume away.
            current_digests[obs_id] = "OBSERVATION_MISSING"
            continue
        file_path = observation_files.get(obs_id)
        if file_path is None or not file_path.exists():
            current_digests[obs_id] = "MISSING"
        else:
            current_digests[obs_id] = sha256_file(file_path)

    reason = staleness_reason(
        source_revision_checked=prepared.source_revision_checked,
        mandate_revision_checked=prepared.mandate_revision_checked,
        current_resource_digests=current_digests,
        current_mandate_revision=current_mandate.revision,
    )
    if reason is not None:
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=[reason, "re-propose this action against current state rather than retry"],
            now=now,
            prev_hash=prev_receipt_hash,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "device": by_id[prepared.resources_touched[0]].source if prepared.resources_touched else None,
        "destination": prepared.destination,
        "excluded_devices": prepared.excluded_sources,
        "included": [],
    }
    for obs_id in prepared.resources_touched:
        obs = by_id[obs_id]
        src = observation_files[obs_id]
        dest = out_dir / f"{obs_id}{src.suffix}"
        shutil.copy2(src, dest)
        manifest["included"].append(
            {
                "observation_id": obs_id,
                "source": obs.source,
                "digest": obs.evidence_custody.integrity_digest,
                "filename": dest.name,
            }
        )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    package_digest = sha256_file(manifest_path)

    payload = {
        "proposed_action_id": proposed_action.id,
        "decision_id": decision.id,
        "verdict": decision.verdict.value,
        "executed": True,
        "package_digest": package_digest,
        "included_count": len(manifest["included"]),
    }
    receipt_hash = seal(payload, prev_receipt_hash)

    return Receipt(
        id=f"receipt-{proposed_action.id}",
        proposed_action_id=proposed_action.id,
        decision_id=decision.id,
        executed=True,
        observed_effect=f"package assembled at {out_dir}, manifest digest {package_digest}",
        prev_hash=prev_receipt_hash,
        hash=receipt_hash,
        created_at=now,
    )


def assemble_evidence_package(
    *,
    proposed_action: ProposedAction,
    mandate: Mandate,
    observations: list[Observation],
    requirements: list[EvidenceRequirement],
    observation_files: dict[str, Path],
    allowed_device: str,
    destination: str,
    out_dir: Path,
    now: datetime,
    prev_receipt_hash: Optional[str] = None,
) -> tuple[Decision, Receipt]:
    """Convenience wrapper: prepare and execute back to back, for
    callers with no real gap between the two (most of the test suite,
    the demo's happy-path run). Callers who want to exercise the staleness
    window should call prepare_evidence_package() and
    execute_prepared_action() directly with something changing in
    between — see tests/test_invalidation.py.
    """
    decision, prepared = prepare_evidence_package(
        proposed_action=proposed_action,
        mandate=mandate,
        observations=observations,
        requirements=requirements,
        observation_files=observation_files,
        allowed_device=allowed_device,
        destination=destination,
        now=now,
    )
    if prepared is None:
        return decision, _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=decision.reasons,
            now=now,
            prev_hash=prev_receipt_hash,
        )
    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=proposed_action,
        observations=observations,
        observation_files=observation_files,
        current_mandate=mandate,
        out_dir=out_dir,
        now=now,
        prev_receipt_hash=prev_receipt_hash,
    )
    return decision, receipt
