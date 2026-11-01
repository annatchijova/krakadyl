"""Level 6 mission continuity across a real-time gap: resume_after_gap reports
what expired or closed between the last activity and now, due to time alone."""

from datetime import datetime, timedelta, timezone

from krakadyl.core.continuity import resume_after_gap
from krakadyl.core.models import (
    EvidenceRequirement,
    Mandate,
    RecoveryWindow,
    RecoveryWindowKind,
    TaskResponsibility,
    TaskStatus,
)

SINCE = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
NOW = SINCE + timedelta(days=3, hours=2)


def _req(req_id, *, until=None, kind=RecoveryWindowKind.KNOWN, resolved=False,
         unresolvable=False, condition=None, estimate_basis=None):
    rw = None
    if kind is not None:
        rw = RecoveryWindow(
            kind=kind, until=until, condition=condition, estimate_basis=estimate_basis,
            what_is_lost_if_missed=f"{req_id} source lost",
        )
    return EvidenceRequirement(
        id=req_id, predicate=f"{req_id} acquired", acceptable_source_class="tool",
        observation_id=f"obs-{req_id}", resolved=resolved, unresolvable=unresolvable,
        responsibility=TaskResponsibility(owner="investigator-A", status=TaskStatus.ASSIGNED),
        recovery_window=rw,
    )


def _mandate(mid, *, valid_until, parent_id=None):
    return Mandate(
        id=mid, issuer="x", principal="investigator-A", resources=["r"], operations=["o"],
        destinations=["d"], valid_from=SINCE - timedelta(days=5), valid_until=valid_until,
        parent_id=parent_id,
    )


def test_gap_duration_is_humanized_in_whole_units():
    b = resume_after_gap(requirements=[], mandates=[], since=SINCE, now=NOW)
    assert b.gap_seconds == int((NOW - SINCE).total_seconds())
    assert b.gap_human == "3 days, 2 hours"


def test_a_mandate_that_expired_during_the_gap_is_reported():
    expired = _mandate("m-root", valid_until=SINCE + timedelta(days=1))   # closed in the gap
    still = _mandate("m-live", valid_until=NOW + timedelta(days=1))       # still valid
    old = _mandate("m-old", valid_until=SINCE - timedelta(days=1))        # expired before the gap
    b = resume_after_gap(requirements=[], mandates=[expired, still, old], since=SINCE, now=NOW)
    assert b.mandates_expired_while_away == ("m-root",)


def test_an_expired_sub_mandate_is_also_flagged_as_a_lapsed_delegation():
    sub = _mandate("m-sub", valid_until=SINCE + timedelta(hours=1), parent_id="m-root")
    b = resume_after_gap(requirements=[], mandates=[sub], since=SINCE, now=NOW)
    assert b.mandates_expired_while_away == ("m-sub",)
    assert b.delegations_expired_while_away == ("m-sub",)


def test_recovery_windows_closed_during_the_gap_are_separated_from_still_open():
    closed = _req("r-closed", until=SINCE + timedelta(hours=6))     # closed in the gap
    before = _req("r-before", until=SINCE - timedelta(hours=1))     # closed before the gap
    open_soon = _req("r-soon", until=NOW + timedelta(hours=2))
    open_later = _req("r-later", until=NOW + timedelta(days=1))
    b = resume_after_gap(
        requirements=[open_later, closed, before, open_soon], mandates=[], since=SINCE, now=NOW
    )
    assert [i.requirement_id for i in b.recovery_closed_while_away] == ["r-closed"]
    # still-open, soonest first
    assert [i.requirement_id for i in b.recovery_still_open] == ["r-soon", "r-later"]


def test_conditional_unknown_and_windowless_open_requirements_go_to_watch():
    cond = _req("r-cond", kind=RecoveryWindowKind.CONDITIONAL, condition="device powered off")
    unk = _req("r-unk", kind=RecoveryWindowKind.UNKNOWN)
    none = _req("r-none", kind=None)
    b = resume_after_gap(requirements=[cond, unk, none], mandates=[], since=SINCE, now=NOW)
    assert set(b.conditional_or_unknown_watch) == {"r-cond", "r-unk", "r-none"}


def test_resolved_and_unresolvable_requirements_are_excluded():
    done = _req("r-done", until=NOW + timedelta(hours=1), resolved=True)
    dead = _req("r-dead", until=NOW + timedelta(hours=1), unresolvable=True)
    b = resume_after_gap(requirements=[done, dead], mandates=[], since=SINCE, now=NOW)
    assert b.recovery_still_open == ()
    assert b.conditional_or_unknown_watch == ()
