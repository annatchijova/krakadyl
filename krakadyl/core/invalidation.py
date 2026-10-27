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
from typing import Optional

from krakadyl.core.models import EvidenceRequirement, Hypothesis, HypothesisStatus


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

    return flagged
