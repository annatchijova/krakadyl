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

from krakadyl.core.models import EvidenceRequirement, EvidenceState, RecoveryWindowKind, TaskStatus


def evidence_state_from_requirement(req: EvidenceRequirement) -> EvidenceState:
    """The one place "reported done" gets turned into an evidence state.

    REPORTED_DONE without verification stays MISSING — a claim is not a
    fact. This is deliberate, not a bug: see TaskResponsibility.is_only_claimed.
    """
    if req.unresolvable:
        return EvidenceState.MISSING
    if req.resolved and req.responsibility.is_verified:
        return EvidenceState.SUFFICIENT
    if req.responsibility.status == TaskStatus.VERIFIED_DONE and not req.resolved:
        return EvidenceState.CONFLICTING
    return EvidenceState.MISSING


class UrgentDiscrepancy(BaseModel):
    requirement_id: str
    reason: str
    minutes_left: Optional[float] = None  # None when the window is CONDITIONAL — flagged anyway


def find_urgent_discrepancies(
    requirements: list[EvidenceRequirement],
    now: datetime,
    urgency_window: timedelta = timedelta(minutes=30),
) -> list[UrgentDiscrepancy]:
    """The mandatory adversarial scenario, as a general check.

    Flags any requirement that is only CLAIMED (not verified):
    - KNOWN/ESTIMATED window: flagged once it's within `urgency_window`.
    - CONDITIONAL window (closes on an event, timing unknown): flagged
      unconditionally while only-claimed — we can't compute "how close,"
      so the honest response is to always surface it rather than
      silently treat unknown timing as "not urgent."
    - UNKNOWN window: not flagged. This is a known, documented gap —
      there is genuinely no information to act on, not a judgment that
      no risk exists. Tracked, not silently claimed to be handled.
    """
    found: list[UrgentDiscrepancy] = []
    for req in requirements:
        if not req.responsibility.is_only_claimed:
            continue
        rw = req.recovery_window
        if rw is None:
            continue

        if rw.kind in (RecoveryWindowKind.KNOWN, RecoveryWindowKind.ESTIMATED) and rw.until:
            minutes_left = (rw.until - now).total_seconds() / 60
            if timedelta(minutes=minutes_left) <= urgency_window:
                basis = f" (estimated — {rw.estimate_basis})" if rw.kind == RecoveryWindowKind.ESTIMATED else ""
                found.append(
                    UrgentDiscrepancy(
                        requirement_id=req.id,
                        reason=(
                            f"'{req.predicate}' was reported done by "
                            f"{req.responsibility.reported_done_by}, but no verification exists, "
                            f"and {rw.what_is_lost_if_missed} in {minutes_left:.0f} minutes{basis}."
                        ),
                        minutes_left=minutes_left,
                    )
                )
        elif rw.kind == RecoveryWindowKind.CONDITIONAL:
            found.append(
                UrgentDiscrepancy(
                    requirement_id=req.id,
                    reason=(
                        f"'{req.predicate}' was reported done by "
                        f"{req.responsibility.reported_done_by}, but no verification exists, "
                        f"and {rw.what_is_lost_if_missed} if {rw.condition} happens — "
                        "timing unknown, flagged regardless."
                    ),
                    minutes_left=None,
                )
            )
        # UNKNOWN kind: deliberately not flagged — see docstring.

    return found


class NextMove(BaseModel):
    """What the invariant actually guarantees: a clear answer, never a
    fabricated single priority where none is defensible.

    - primary set: one defensible recommendation, ranked on
      recovery-window urgency alone (KNOWN/ESTIMATED windows only —
      see `conditional_watch` for what can't be time-ranked).
    - primary None, uncertain True: two or more candidates share the
      same most-urgent window — the honest answer is "no single
      defensible priority," not an arbitrary pick.
    - `conditional_watch`: open requirements whose recovery window is
      CONDITIONAL or UNKNOWN — they can't be time-ranked against the
      others, so instead of silently sinking to the bottom of a
      priority list they stay visible here, separately.
    - `blocked`: requirements with a legitimate claim on attention that
      the agent currently has no authorized path for.

    `dependents_count` (requirement id -> count of *distinct*
    hypothesis ids) is exposed alongside the ranking, never folded into
    it — see the Oct 27 correction below. **Known, tracked limitation,
    not silently claimed solved**: this counts whatever hypothesis ids
    are listed, not only ones a human or the policy engine has marked
    "accepted" — an agent that generates many superficial hypotheses
    could still inflate the number shown here, even though it can no
    longer change which requirement gets picked as primary. Filtering
    to accepted hypotheses needs Hypothesis objects passed in, which
    this function doesn't take yet.
    """

    primary: Optional[str] = None  # requirement id
    alternatives: list[str] = []
    uncertain: bool = False
    blocked: list[tuple[str, str]] = []  # (requirement id, reason)
    conditional_watch: list[str] = []
    dependents_count: dict[str, int] = {}


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

    def dependents(r: EvidenceRequirement) -> int:
        if r.recovery_window is None:
            return 0
        # Deduplicated — correction from the Oct 27 review: a repeated
        # id must not inflate the count.
        return len(set(r.recovery_window.depends_on_hypothesis_ids))

    dependents_count = {r.id: dependents(r) for r in open_candidates}

    def is_rankable(r: EvidenceRequirement) -> bool:
        rw = r.recovery_window
        return rw is not None and rw.kind in (RecoveryWindowKind.KNOWN, RecoveryWindowKind.ESTIMATED) and rw.until is not None

    def is_watch_only(r: EvidenceRequirement) -> bool:
        # No recovery_window at all is treated the same as UNKNOWN: real
        # open work, but nothing to time-rank it against — stays visible
        # in conditional_watch instead of silently vanishing.
        rw = r.recovery_window
        return rw is None or rw.kind in (RecoveryWindowKind.CONDITIONAL, RecoveryWindowKind.UNKNOWN)

    conditional_watch = [r.id for r in open_candidates if is_watch_only(r)]
    rankable = [r for r in open_candidates if is_rankable(r)]

    if not open_candidates:
        return NextMove(
            primary=None,
            alternatives=[],
            uncertain=False,
            blocked=blocked,
            conditional_watch=[],
            dependents_count={},
        )

    if not rankable:
        # Everything open is CONDITIONAL/UNKNOWN — nothing to time-rank,
        # but there is open work. Honest answer: uncertain, not empty.
        return NextMove(
            primary=None,
            alternatives=[r.id for r in open_candidates],
            uncertain=True,
            blocked=blocked,
            conditional_watch=conditional_watch,
            dependents_count=dependents_count,
        )

    def urgency_rank(r: EvidenceRequirement) -> float:
        if r.recovery_window is None or r.recovery_window.until is None:
            return float("inf")
        return r.recovery_window.until.timestamp()

    # Urgency is the ONLY automatic ranking key — hypothesis-dependent
    # count is deliberately not a tiebreaker, see class docstring.
    ranked = sorted(rankable, key=lambda r: (urgency_rank(r), r.id))
    top = ranked[0]
    tied_with_top = [r for r in ranked if urgency_rank(r) == urgency_rank(top)]

    if len(tied_with_top) > 1:
        return NextMove(
            primary=None,
            alternatives=[r.id for r in ranked],
            uncertain=True,
            blocked=blocked,
            conditional_watch=conditional_watch,
            dependents_count=dependents_count,
        )

    return NextMove(
        primary=top.id,
        alternatives=[r.id for r in ranked[1:]],
        uncertain=False,
        blocked=blocked,
        conditional_watch=conditional_watch,
        dependents_count=dependents_count,
    )
