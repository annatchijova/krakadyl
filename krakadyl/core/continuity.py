"""Operational and cognitive continuity — docs/levels.md invariants 4, 5, 6.

The system is the external memory. A claim that something was done is
never read as proof that it was done, and a requirement sitting on an
expiring source is never allowed to go quiet just because someone
reported it handled.

Uncertainty about whether something happened is information that gets
preserved as its own state (REPORTED_DONE), never collapsed back into
"didn't happen" or "unknown."
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel

from krakadyl.core.models import EvidenceRequirement, EvidenceState, TaskStatus


def evidence_state_from_requirement(req: EvidenceRequirement) -> EvidenceState:
    """The one place "reported done" gets turned into an evidence state.

    REPORTED_DONE without verification stays MISSING — a claim is not a
    fact. This is deliberate, not a bug: see Custody.is_only_claimed.
    """
    if req.unresolvable:
        return EvidenceState.MISSING
    if req.resolved and req.custody.is_verified:
        return EvidenceState.SUFFICIENT
    if req.custody.status == TaskStatus.VERIFIED_DONE and not req.resolved:
        return EvidenceState.CONFLICTING
    return EvidenceState.MISSING


class UrgentDiscrepancy(BaseModel):
    requirement_id: str
    reason: str
    minutes_left: float


def find_urgent_discrepancies(
    requirements: list[EvidenceRequirement],
    now: datetime,
    urgency_window: timedelta = timedelta(minutes=30),
) -> list[UrgentDiscrepancy]:
    """The mandatory adversarial scenario, as a general check.

    Flags any requirement that is only CLAIMED (not verified), while its
    recovery window is about to close — the exact shape of "an
    investigator reports a critical source preserved, a teammate closes
    the task, and no acquisition receipt exists while the source has
    twenty minutes left." This never silently lets the case file present
    that evidence as preserved.
    """
    found: list[UrgentDiscrepancy] = []
    for req in requirements:
        if not req.custody.is_only_claimed:
            continue
        if req.recovery_window is None or req.recovery_window.until is None:
            continue
        minutes_left = (req.recovery_window.until - now).total_seconds() / 60
        if timedelta(minutes=minutes_left) <= urgency_window:
            found.append(
                UrgentDiscrepancy(
                    requirement_id=req.id,
                    reason=(
                        f"'{req.predicate}' was reported done by "
                        f"{req.custody.reported_done_by}, but no verification exists, "
                        f"and {req.recovery_window.what_is_lost_if_missed} "
                        f"in {minutes_left:.0f} minutes."
                    ),
                    minutes_left=minutes_left,
                )
            )
    return found


class NextMove(BaseModel):
    """What the invariant actually guarantees: a clear answer, never a
    fabricated single priority where none is defensible.

    - primary set, alternatives possibly non-empty, uncertain False:
      the normal case — one defensible recommendation.
    - primary None, uncertain True: two or more candidates are tied on
      every criterion that would break the tie — the honest answer is
      "no single defensible priority," not an arbitrary pick. Both/all
      tied candidates are in `alternatives`.
    - primary None, uncertain False, alternatives empty: nothing open.
    - `blocked` always lists requirements with a legitimate claim on
      attention that the agent currently has no authorized path for —
      visible, not hidden, even though they're not actionable now.
    """

    primary: Optional[str] = None  # requirement id
    alternatives: list[str] = []
    uncertain: bool = False
    blocked: list[tuple[str, str]] = []  # (requirement id, reason)


def next_move(requirements: list[EvidenceRequirement]) -> NextMove:
    blocked = [
        (r.id, r.blocked_reason or "blocked by authority")
        for r in requirements
        if r.blocked_by_authority
    ]

    open_candidates = [
        r
        for r in requirements
        if not r.resolved and not r.unresolvable and not r.blocked_by_authority
    ]

    if not open_candidates:
        return NextMove(primary=None, alternatives=[], uncertain=False, blocked=blocked)

    def urgency_rank(r: EvidenceRequirement) -> float:
        if r.recovery_window is None or r.recovery_window.until is None:
            return float("inf")
        return r.recovery_window.until.timestamp()

    def dependents(r: EvidenceRequirement) -> int:
        if r.recovery_window is None:
            return 0
        return len(r.recovery_window.depends_on_hypothesis_ids)

    ranked = sorted(open_candidates, key=lambda r: (urgency_rank(r), -dependents(r)))
    top = ranked[0]
    tied_with_top = [
        r
        for r in ranked
        if urgency_rank(r) == urgency_rank(top) and dependents(r) == dependents(top)
    ]

    if len(tied_with_top) > 1:
        return NextMove(
            primary=None,
            alternatives=[r.id for r in ranked],
            uncertain=True,
            blocked=blocked,
        )

    return NextMove(
        primary=top.id,
        alternatives=[r.id for r in ranked[1:]],
        uncertain=False,
        blocked=blocked,
    )
