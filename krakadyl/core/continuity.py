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

from pydantic import BaseModel, ConfigDict

from krakadyl.core.models import (
    EvidenceRequirement,
    EvidenceState,
    Mandate,
    RecoveryWindowKind,
    TaskStatus,
)


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


# --- Level 6: re-orientation after a long real-time gap ------------------
#
# next_move answers "what now" from the current requirement set, but it ranks
# windows by absolute `until` and does not know how much real time has passed —
# a window that closed while the investigator was away would still be ranked as
# if it were open. resume_after_gap is the long-gap companion: given the moment
# of the last recorded activity and now, it reports what crossed a threshold
# *while away* purely because time passed — mandates (and delegations) that
# expired, recovery windows that closed — so a case picked up after days or
# weeks is not silently treated as if nothing moved. It is a pure read: no
# authority changes, nothing is mutated, and no float enters (durations are
# integer seconds).


class GapItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    requirement_id: str
    what_is_lost_if_missed: str
    at: Optional[datetime] = None  # the window's `until` (closed, or still-open deadline)


class ResumeBriefing(BaseModel):
    """What changed on a case between the last recorded activity and now, due to
    elapsed time alone. The forward-looking "what now" stays with next_move;
    this is strictly the then->now diff a returning investigator would otherwise
    have to reconstruct by hand."""

    model_config = ConfigDict(frozen=True)

    gap_seconds: int
    gap_human: str
    mandates_expired_while_away: tuple[str, ...] = ()
    delegations_expired_while_away: tuple[str, ...] = ()
    recovery_closed_while_away: tuple[GapItem, ...] = ()
    recovery_still_open: tuple[GapItem, ...] = ()
    conditional_or_unknown_watch: tuple[str, ...] = ()
    headline: str


def _humanize_gap(seconds: int) -> str:
    """Integer-only human duration — no float reaches any sealed or decision
    path, and this string is cosmetic regardless."""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    parts = []
    for label, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count} {label}{'s' if count != 1 else ''}")
    return ", ".join(parts) if parts else "under a minute"


def resume_after_gap(
    *,
    requirements: list[EvidenceRequirement],
    mandates: list[Mandate],
    since: datetime,
    now: datetime,
) -> ResumeBriefing:
    """Re-orientation for a case picked up after a real-time gap. `since` is the
    last recorded activity; `now` is the moment of return. Reports what expired
    or closed in the half-open interval (since, now] and what recovery windows
    are still open, ranked soonest first. Does not rank by a fabricated urgency
    horizon and does not touch authority — a window still open is reported with
    its deadline, not a verdict."""
    gap_seconds = max(int((now - since).total_seconds()), 0)

    expired: list[str] = []
    delegations_expired: list[str] = []
    for m in mandates:
        if m.valid_until is not None and since < m.valid_until <= now:
            expired.append(m.id)
            if m.parent_id is not None:
                delegations_expired.append(m.id)

    closed: list[GapItem] = []
    still_open: list[GapItem] = []
    watch: list[str] = []
    for r in requirements:
        if r.resolved or r.unresolvable or r.blocked_by_authority:
            continue
        rw = r.recovery_window
        if rw is None or rw.kind in (RecoveryWindowKind.CONDITIONAL, RecoveryWindowKind.UNKNOWN):
            watch.append(r.id)
            continue
        if rw.until is None:
            watch.append(r.id)
            continue
        item = GapItem(requirement_id=r.id, what_is_lost_if_missed=rw.what_is_lost_if_missed, at=rw.until)
        if rw.until <= now:
            # Closed. Only count it as "while away" if it was still open at the
            # last activity — a window already closed before the gap is old news.
            if rw.until > since:
                closed.append(item)
        else:
            still_open.append(item)

    still_open.sort(key=lambda i: i.at)  # soonest deadline first
    headline = (
        f"Picked up after {_humanize_gap(gap_seconds)}: "
        f"{len(expired)} mandate(s) expired and {len(closed)} recovery window(s) closed while away; "
        f"{len(still_open)} still open, {len(watch)} on conditional/unknown watch."
    )
    return ResumeBriefing(
        gap_seconds=gap_seconds,
        gap_human=_humanize_gap(gap_seconds),
        mandates_expired_while_away=tuple(expired),
        delegations_expired_while_away=tuple(delegations_expired),
        recovery_closed_while_away=tuple(closed),
        recovery_still_open=tuple(still_open),
        conditional_or_unknown_watch=tuple(watch),
        headline=headline,
    )
