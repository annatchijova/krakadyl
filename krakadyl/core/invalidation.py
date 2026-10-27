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
