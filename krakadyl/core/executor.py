"""The real domain action: assembling a verifiable local evidence package.

This is Level 1's stated acceptance criterion — one real action executed
end-to-end, not simulated. It's the first place models, policy, and
receipt actually wire together into a pipeline instead of being tested
in isolation.

The flow, every time, no shortcuts: resolve authority via the mandate
(never trust the caller's claim of what device is "allowed"), verify
every included observation's integrity against the real file on disk
(never trust a stored digest without recomputing it), call decide()
for the verdict, and only execute if the verdict is ALLOWED. FORBIDDEN
and CONFIRM paths still produce a Receipt — recording that nothing was
done, and why, is as real an outcome as doing something.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from krakadyl.core.models import (
    AuthorityState,
    AuthorityVerdict,
    Decision,
    EvidenceState,
    Mandate,
    Observation,
    ProposedAction,
    Receipt,
)
from krakadyl.core.policy import decide
from krakadyl.core.receipt import seal


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


def assemble_evidence_package(
    *,
    proposed_action: ProposedAction,
    mandate: Mandate,
    observations: list[Observation],
    observation_files: dict[str, Path],  # observation id -> real file on disk
    allowed_device: str,
    destination: str,
    out_dir: Path,
    now: datetime,
    prev_receipt_hash: Optional[str] = None,
) -> tuple[Decision, Receipt]:
    """Resolves authority and evidence integrity for real, then executes
    only if ALLOWED. Always returns a Decision and a Receipt — the
    Receipt's `executed` field says whether anything actually ran.
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

    integrity_failures = [
        o.id for o in included if not verify_observation_integrity(o, observation_files[o.id])
    ]
    if integrity_failures:
        evidence_state = EvidenceState.CONFLICTING
    elif not included:
        evidence_state = EvidenceState.MISSING
    else:
        evidence_state = EvidenceState.SUFFICIENT

    verdict, policy_reasons = decide(
        evidence_state=evidence_state,
        authority_state=check.authority_state,
        outside_mandate_scope=check.outside_scope,
        resolvable_by_authorized_source=False,  # no re-acquisition path modeled yet (Level 2)
    )
    reasons = check.reasons + policy_reasons
    if integrity_failures:
        reasons.append(f"integrity check failed for: {', '.join(integrity_failures)}")

    decision = Decision(
        id=f"decision-{proposed_action.id}",
        proposed_action_id=proposed_action.id,
        verdict=verdict,
        evidence_state=evidence_state,
        authority_state=check.authority_state,
        reasons=reasons,
        decided_at=now,
    )

    payload = {
        "proposed_action_id": proposed_action.id,
        "decision_id": decision.id,
        "verdict": verdict.value,
    }

    if verdict != AuthorityVerdict.ALLOWED:
        payload["executed"] = False
        effect = "not executed: " + "; ".join(reasons)
        receipt_hash = seal(payload, prev_receipt_hash)
        return decision, Receipt(
            id=f"receipt-{proposed_action.id}",
            proposed_action_id=proposed_action.id,
            decision_id=decision.id,
            executed=False,
            observed_effect=effect,
            prev_hash=prev_receipt_hash,
            hash=receipt_hash,
            created_at=now,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "device": allowed_device,
        "destination": destination,
        "excluded_devices": excluded_devices,
        "included": [],
    }
    for obs in included:
        src = observation_files[obs.id]
        dest = out_dir / f"{obs.id}{src.suffix}"
        shutil.copy2(src, dest)
        manifest["included"].append(
            {
                "observation_id": obs.id,
                "source": obs.source,
                "digest": obs.evidence_custody.integrity_digest,
                "filename": dest.name,
            }
        )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    package_digest = sha256_file(manifest_path)

    payload["executed"] = True
    payload["package_digest"] = package_digest
    payload["included_count"] = len(manifest["included"])
    receipt_hash = seal(payload, prev_receipt_hash)

    return decision, Receipt(
        id=f"receipt-{proposed_action.id}",
        proposed_action_id=proposed_action.id,
        decision_id=decision.id,
        executed=True,
        observed_effect=f"package assembled at {out_dir}, manifest digest {package_digest}",
        prev_hash=prev_receipt_hash,
        hash=receipt_hash,
        created_at=now,
    )
