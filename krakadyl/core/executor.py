"""The real domain action: assembling a verifiable local evidence package.

Two phases, not one: `prepare_evidence_package` resolves authority and
evidence state and produces a `PreparedAction` snapshot (Decision made,
nothing executed yet); `execute_prepared_action` fully revalidates that
snapshot — mandate (scope, validity window, revocation), the
EvidenceRequirements it depends on, correspondence between the objects
passed in, and resource integrity — immediately before acting. Nothing
from `prepare` time is trusted at `execute` time without being checked
again; the one exception, unavoidable without a persistence layer (the
next piece of work), is that the caller still has to hand both calls
the same `observations`/`requirements` collections — there is no store
yet that owns that state independently. `assemble_evidence_package` is a
thin convenience wrapper calling both back to back, for callers with no
real gap between the two.

Fixed 2026-10-27 (follow-up review, commit 0ea6db6): `execute` used to
only check the PreparedAction's expiry and a revision-string comparison
— it never re-ran the mandate check (so a mandate expiring, or starting
in the future, between prepare and execute wasn't caught the same way
prepare would have caught it), never re-checked EvidenceRequirements
(so a requirement reverted from VERIFIED_DONE after prepare wasn't
caught), never checked that `prepared`/`decision`/`proposed_action`
actually corresponded to each other, and had no replay protection for
executing the same PreparedAction twice.
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
from krakadyl.core.invalidation import compute_combined_revision
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


class PackageAssemblyError(Exception):
    pass


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
    checked against a Mandate. Nothing downstream re-derives this —
    both `prepare_evidence_package` and `execute_prepared_action` call
    this same function, at their own respective times.
    """
    if mandate.revoked:
        return MandateCheck(
            outside_scope=True,
            authority_state=AuthorityState.DENIED,
            reasons=[f"mandate revoked: {mandate.revoked_reason}"],
        )
    if now < mandate.valid_from:
        # Found in the Oct 27 follow-up review: only valid_until was
        # checked — a mandate dated to start in the future was treated
        # as already granted. No human confirmation can make a mandate
        # valid before its own start — DENIED, same as outside scope.
        return MandateCheck(
            outside_scope=True,
            authority_state=AuthorityState.DENIED,
            reasons=[f"mandate does not take effect until {mandate.valid_from.isoformat()}"],
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


@dataclass
class EvidenceCheck:
    evidence_state: EvidenceState
    included: list[Observation]
    excluded_devices: list[str]
    integrity_failures: list[str]
    unverified: list[str]
    reasons: list[str]


def check_evidence(
    observations: list[Observation],
    requirements: list[EvidenceRequirement],
    *,
    allowed_device: str,
    observation_files: dict[str, Path],
) -> EvidenceCheck:
    """The one place evidence state gets derived — used by both
    `prepare_evidence_package` and `execute_prepared_action`, so the two
    can never silently diverge on what "sufficient evidence" means.

    Sufficient only when BOTH hold, for every included observation: its
    `EvidenceRequirement` independently reached `VERIFIED_DONE` (via
    `continuity.evidence_state_from_requirement`), and its file's digest
    still matches what was acquired. Neither substitutes for the other.
    """
    included = [o for o in observations if o.source == allowed_device]
    excluded_devices = sorted({o.source for o in observations if o.source != allowed_device})
    requirements_by_observation = {r.observation_id: r for r in requirements if r.observation_id}

    integrity_failures = [
        o.id for o in included if not verify_observation_integrity(o, observation_files.get(o.id, Path("/nonexistent")))
    ]

    unverified: list[str] = []
    for o in included:
        req = requirements_by_observation.get(o.id)
        if req is None:
            unverified.append(f"{o.id} (no EvidenceRequirement governs its acquisition)")
        elif evidence_state_from_requirement(req) != EvidenceState.SUFFICIENT:
            unverified.append(
                f"{o.id} (requirement '{req.id}' is {req.responsibility.status.value}, not independently verified)"
            )

    reasons: list[str] = []
    if integrity_failures:
        evidence_state = EvidenceState.CONFLICTING
        reasons.append(f"integrity check failed for: {', '.join(integrity_failures)}")
    elif not included:
        evidence_state = EvidenceState.MISSING
    elif unverified:
        evidence_state = EvidenceState.MISSING
        reasons.append(f"not independently verified: {', '.join(unverified)}")
    else:
        evidence_state = EvidenceState.SUFFICIENT

    return EvidenceCheck(
        evidence_state=evidence_state,
        included=included,
        excluded_devices=excluded_devices,
        integrity_failures=integrity_failures,
        unverified=unverified,
        reasons=reasons,
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
    """
    resource = f"{proposed_action.mission_id}/{allowed_device}"
    mandate_check = check_mandate(
        mandate,
        resource=resource,
        operation=proposed_action.operation,
        destination=destination,
        now=now,
    )
    evidence_check = check_evidence(
        observations, requirements, allowed_device=allowed_device, observation_files=observation_files
    )

    verdict, policy_reasons = decide(
        evidence_state=evidence_check.evidence_state,
        authority_state=mandate_check.authority_state,
        outside_mandate_scope=mandate_check.outside_scope,
        resolvable_by_authorized_source=False,  # no re-acquisition path modeled yet (Level 3)
    )
    # Evidence-check reasons (integrity/verification detail naming the
    # specific observation) come last, not before policy_reasons — tests
    # and downstream readers key off reasons[-1] for the most specific,
    # actionable detail; a generic policy reason must never bury it.
    reasons = mandate_check.reasons + policy_reasons + evidence_check.reasons

    decision = Decision(
        id=f"decision-{proposed_action.id}",
        proposed_action_id=proposed_action.id,
        verdict=verdict,
        evidence_state=evidence_check.evidence_state,
        authority_state=mandate_check.authority_state,
        reasons=reasons,
        decided_at=now,
    )

    if verdict != AuthorityVerdict.ALLOWED:
        return decision, None

    resource_digests = {o.id: o.evidence_custody.integrity_digest for o in evidence_check.included}
    combined_revision = compute_combined_revision(resource_digests)
    prepared = PreparedAction(
        id=f"prepared-{proposed_action.id}",
        proposed_action_id=proposed_action.id,
        payload_digest=combined_revision,
        resource=resource,
        operation=proposed_action.operation,
        destination=destination,
        resources_touched=tuple(o.id for o in evidence_check.included),
        excluded_sources=tuple(evidence_check.excluded_devices),
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
    requirements: list[EvidenceRequirement],
    observation_files: dict[str, Path],
    current_mandate: Mandate,
    consumed_nonces: set[str],
    out_dir: Path,
    now: datetime,
    prev_receipt_hash: Optional[str] = None,
) -> Receipt:
    """Fully revalidates against the CURRENT state before doing anything
    — nothing from `prepare` time is trusted here without being checked
    again. `consumed_nonces` is required, not optional: the caller owns
    its lifetime (today, in memory; once persistence exists, backed by
    storage), and forgetting to pass one is a louder bug than silently
    allowing replay.
    """
    if not (prepared.proposed_action_id == proposed_action.id == decision.proposed_action_id):
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=["prepared/decision/proposed_action do not correspond to the same action"],
            now=now,
            prev_hash=prev_receipt_hash,
        )
    if decision.verdict != AuthorityVerdict.ALLOWED:
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=[f"decision verdict is {decision.verdict.value}, not ALLOWED"],
            now=now,
            prev_hash=prev_receipt_hash,
        )
    if prepared.nonce in consumed_nonces:
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=["this PreparedAction was already executed (nonce replay)"],
            now=now,
            prev_hash=prev_receipt_hash,
        )
    if now > prepared.expires_at:
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=[f"PreparedAction expired at {prepared.expires_at.isoformat()}"],
            now=now,
            prev_hash=prev_receipt_hash,
        )

    mandate_check = check_mandate(
        current_mandate,
        resource=prepared.resource,
        operation=prepared.operation,
        destination=prepared.destination,
        now=now,
    )
    if mandate_check.authority_state != AuthorityState.GRANTED or mandate_check.outside_scope:
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=["mandate no longer grants this action: " + "; ".join(mandate_check.reasons)],
            now=now,
            prev_hash=prev_receipt_hash,
        )
    if current_mandate.revision != prepared.mandate_revision_checked:
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=[
                f"mandate revision changed since this action was prepared "
                f"(checked against '{prepared.mandate_revision_checked}', now '{current_mandate.revision}')"
            ],
            now=now,
            prev_hash=prev_receipt_hash,
        )

    # The device string lives in prepared.resource ("mission_id/device")
    # — the single source of truth from prepare time, not re-derived
    # from whatever observations happens to contain at execute time.
    allowed_device = prepared.resource.rsplit("/", 1)[-1]
    evidence_check = check_evidence(
        observations,
        requirements,
        allowed_device=allowed_device,
        observation_files=observation_files,
    )
    current_resource_digests = {
        o.id: o.evidence_custody.integrity_digest
        for o in evidence_check.included
        if o.id in prepared.resources_touched
    }
    current_source_revision = compute_combined_revision(current_resource_digests)
    if evidence_check.evidence_state != EvidenceState.SUFFICIENT:
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=["evidence no longer sufficient at execution time: " + "; ".join(evidence_check.reasons)],
            now=now,
            prev_hash=prev_receipt_hash,
        )
    if current_source_revision != prepared.source_revision_checked:
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=["one or more source resources changed since this action was prepared"],
            now=now,
            prev_hash=prev_receipt_hash,
        )

    by_id = {o.id: o for o in observations}
    tmp_dir = out_dir.with_name(out_dir.name + f".tmp-{prepared.nonce}")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        manifest = {
            "device": by_id[prepared.resources_touched[0]].source if prepared.resources_touched else None,
            "destination": prepared.destination,
            "excluded_devices": list(prepared.excluded_sources),
            "included": [],
        }
        for obs_id in prepared.resources_touched:
            obs = by_id[obs_id]
            src = observation_files[obs_id]
            dest = tmp_dir / f"{obs_id}{src.suffix}"
            shutil.copy2(src, dest)
            copied_digest = sha256_file(dest)
            if copied_digest != obs.evidence_custody.integrity_digest:
                # Caught by self-red-teaming the Oct 27 follow-up: a file
                # that changes WHILE being copied (or a copy that silently
                # corrupts) must never be published as if it matched.
                raise PackageAssemblyError(
                    f"copied file for {obs_id} does not match its expected digest "
                    "(changed during copy, or the copy itself is corrupt)"
                )
            manifest["included"].append(
                {
                    "observation_id": obs_id,
                    "source": obs.source,
                    "digest": obs.evidence_custody.integrity_digest,
                    "filename": dest.name,
                }
            )
        manifest_path = tmp_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        package_digest = sha256_file(manifest_path)
    except PackageAssemblyError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return _not_executed_receipt(
            proposed_action=proposed_action,
            decision=decision,
            reasons=[f"package assembly failed, nothing published: {exc}"],
            now=now,
            prev_hash=prev_receipt_hash,
        )

    # Publish atomically — only now does anything become visible at
    # out_dir. A failure above never leaves a half-written package that
    # could be mistaken for a complete one.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    tmp_dir.rename(out_dir)

    consumed_nonces.add(prepared.nonce)

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
    consumed_nonces: Optional[set[str]] = None,
    prev_receipt_hash: Optional[str] = None,
) -> tuple[Decision, Receipt]:
    """Convenience wrapper: prepare and execute back to back, for
    callers with no real gap between the two. `consumed_nonces` defaults
    to a fresh set per call, since one-shot callers have no replay
    concern across calls they don't share state between; pass your own
    set explicitly if you're calling this repeatedly and want replay
    protection across those calls.
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
        requirements=requirements,
        observation_files=observation_files,
        current_mandate=mandate,
        consumed_nonces=consumed_nonces if consumed_nonces is not None else set(),
        out_dir=out_dir,
        now=now,
        prev_receipt_hash=prev_receipt_hash,
    )
    return decision, receipt
