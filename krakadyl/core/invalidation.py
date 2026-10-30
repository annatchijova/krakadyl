"""Level 2 — dependency invalidation.

A `PreparedAction` is a snapshot: "this is safe to do, checked against
this revision of the mandate and these resource digests." Time passes
between preparing an action and executing it — a mandate can be revised
or revoked, a source file can change. Per the architecture's own rule
("the executor revalidates state immediately before acting, never just
trusts a decision made earlier"), this module is the one place that
revalidation happens.

Nothing here decides authority — it only answers "is the snapshot this
PreparedAction was built from still the current state?" The verdict
itself still comes from policy.decide() if a re-decision is needed.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from krakadyl.core.continuity import evidence_state_from_requirement
from krakadyl.core.models import (
    EvidenceRequirement,
    EvidenceState,
    Hypothesis,
    HypothesisStatus,
    Observation,
    TaskResponsibility,
    TaskStatus,
)
from krakadyl.core.verification import validate_verification_dependencies


def compute_combined_revision(resource_digests: dict[str, str]) -> str:
    """A single revision string standing in for the state of every
    resource a PreparedAction touches, recomputable later from whatever
    the current digests are. Canonical (sorted keys, compact
    separators) so the same logical state always hashes the same way.
    """
    canon = json.dumps(resource_digests, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def staleness_reason(
    *,
    source_revision_checked: str,
    mandate_revision_checked: str,
    current_resource_digests: dict[str, str],
    current_mandate_revision: str,
) -> Optional[str]:
    """None means still valid. Checked in a fixed order — mandate first,
    since a revoked/changed mandate is the more serious reason, and the
    reason returned should name the more important thing that moved.
    """
    if mandate_revision_checked != current_mandate_revision:
        return (
            f"mandate revision changed since this action was prepared "
            f"(checked against '{mandate_revision_checked}', now '{current_mandate_revision}')"
        )
    current_source_revision = compute_combined_revision(current_resource_digests)
    if source_revision_checked != current_source_revision:
        return "one or more source resources changed since this action was prepared"
    return None


def find_hypotheses_needing_review(
    hypotheses: list[Hypothesis],
    requirements: list[EvidenceRequirement],
    *,
    observations: Optional[list[Observation]] = None,
    observation_files: Optional[dict[str, Path]] = None,
) -> list[tuple[str, str]]:
    """The other half of Level 2: a Hypothesis whose discriminating
    requirement stopped being resolved (or became unresolvable) needs
    human re-review — the observation that discriminated it may no
    longer support that discrimination. A rejected hypothesis is
    skipped (already closed, re-flagging it is noise); an accepted one
    is NOT skipped — accepting something based on evidence that later
    turns out unresolvable is exactly the case this exists to catch.

    Pure query, same style as find_urgent_discrepancies/next_move: it
    surfaces what needs attention, it doesn't mutate anything.
    """
    requirements_by_id = {r.id: r for r in requirements}
    observations_by_id = {o.id: o for o in observations or []}
    flagged: list[tuple[str, str]] = []

    for h in hypotheses:
        if h.status == HypothesisStatus.REJECTED:
            continue
        if h.discriminating_requirement_id is None:
            continue

        req = requirements_by_id.get(h.discriminating_requirement_id)
        if req is None:
            flagged.append(
                (
                    h.id,
                    f"discriminating requirement '{h.discriminating_requirement_id}' "
                    "no longer exists in this case",
                )
            )
            continue
        if req.unresolvable:
            flagged.append(
                (h.id, f"discriminating requirement '{req.id}' became unresolvable: {req.unresolvable_reason}")
            )
            continue
        if not req.resolved:
            flagged.append((h.id, f"discriminating requirement '{req.id}' is no longer resolved"))
            continue
        if req.observation_id and observations is not None and observation_files is not None:
            observation = observations_by_id.get(req.observation_id)
            if observation is None:
                flagged.append(
                    (h.id, f"verification observation '{req.observation_id}' no longer exists")
                )
                continue
            if observation.invalidated:
                flagged.append(
                    (
                        h.id,
                        f"verification observation '{observation.id}' was invalidated: "
                        f"{observation.invalidation_reason}",
                    )
                )
                continue
            failures = validate_verification_dependencies(req, observations, observation_files)
            if failures:
                flagged.append(
                    (h.id, f"verification dependencies for '{req.id}' are invalid: {'; '.join(failures)}")
                )

    return flagged


@dataclass
class HypothesisRecoveryOutcome:
    """A reviewable next question, never an evidentiary verdict."""

    attempted: bool
    suggested_new_requirement: Optional[EvidenceRequirement]
    closed_reason: Optional[str]


def propose_hypothesis_recovery(
    hypothesis: Hypothesis,
    requirements: list[EvidenceRequirement],
    *,
    alternative_source_requirement_id: Optional[str] = None,
    observations: Optional[list[Observation]] = None,
    observation_files: Optional[dict[str, Path]] = None,
) -> HypothesisRecoveryOutcome:
    """Propose a fresh discriminating question after one becomes impossible.

    A caller must identify another requirement already in this case as
    provenance for the alternative source class. This function never
    infers that a source exists from prose, reuses observation custody,
    relinks the hypothesis, or marks the proposed work resolved.
    """

    def close(reason: str) -> HypothesisRecoveryOutcome:
        return HypothesisRecoveryOutcome(
            attempted=False,
            suggested_new_requirement=None,
            closed_reason=reason,
        )

    duplicate_ids = sorted(
        req_id for req_id, count in Counter(r.id for r in requirements).items() if count > 1
    )
    if duplicate_ids:
        return close(f"duplicate requirement id makes recovery ambiguous: {', '.join(duplicate_ids)}")

    flagged = find_hypotheses_needing_review([hypothesis], requirements)
    if not flagged:
        return close("hypothesis is not flagged for review — recovery does not apply")

    requirements_by_id = {r.id: r for r in requirements}
    failed_id = hypothesis.discriminating_requirement_id
    failed = requirements_by_id.get(failed_id) if failed_id is not None else None
    if failed is None:
        return close(
            f"discriminating requirement '{failed_id}' no longer exists; "
            "its predicate and source provenance cannot be reconstructed honestly"
        )
    if not failed.unresolvable:
        return close(
            f"discriminating requirement '{failed.id}' is still open; "
            "continue it instead of creating a duplicate"
        )
    if not failed.predicate.strip() or not failed.acceptable_source_class.strip():
        return close("the failed requirement lacks a usable predicate or source provenance")
    if failed.observation_id is not None:
        return close(
            "the failed requirement governs a concrete observation; recovery cannot "
            "silently detach or duplicate that custody relationship"
        )
    if failed.blocked_by_authority or failed.blocked_reason:
        return close("the failed requirement is blocked by authority; recovery cannot create permission")
    if alternative_source_requirement_id is None:
        return close("no alternative source requirement was explicitly selected from this case")

    source = requirements_by_id.get(alternative_source_requirement_id)
    if source is None:
        return close(
            f"alternative source requirement '{alternative_source_requirement_id}' "
            "does not exist in this case"
        )
    if source.id == failed.id:
        return close("the unresolvable requirement cannot serve as its own alternative source")
    if not source.acceptable_source_class.strip():
        return close("the selected alternative has no declared source class")
    if source.unresolvable:
        return close("the selected alternative source requirement is itself unresolvable")
    if source.blocked_by_authority or source.blocked_reason:
        return close("the selected alternative source requirement is blocked by authority")
    if source.verification_records:
        if observations is None or observation_files is None:
            return close(
                "structured alternative source verification requires current observation context"
            )
        failures = validate_verification_dependencies(source, observations, observation_files)
        if failures:
            return close("alternative source verification dependencies are invalid: " + "; ".join(failures))
    if evidence_state_from_requirement(source) != EvidenceState.SUFFICIENT:
        return close("the selected alternative source requirement is not independently verified")

    identity = json.dumps(
        [hypothesis.id, failed.id, source.id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    recovery_id = f"req-hypothesis-recovery-{hashlib.sha256(identity).hexdigest()}"
    if recovery_id in requirements_by_id:
        return close(f"recovery proposal '{recovery_id}' already exists")

    suggestion = EvidenceRequirement(
        id=recovery_id,
        predicate=failed.predicate,
        acceptable_source_class=source.acceptable_source_class,
        freshness_requirement=failed.freshness_requirement,
        observation_id=None,
        resolved=False,
        unresolvable=False,
        unresolvable_reason=None,
        recovery_window=None,
        blocked_by_authority=False,
        blocked_reason=None,
        responsibility=TaskResponsibility(
            owner=failed.responsibility.owner,
            status=TaskStatus.UNASSIGNED,
        ),
    )
    return HypothesisRecoveryOutcome(
        attempted=True,
        suggested_new_requirement=suggestion,
        closed_reason=None,
    )
