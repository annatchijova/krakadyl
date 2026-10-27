from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from krakadyl.core.continuity import (
    evidence_state_from_requirement,
    find_urgent_discrepancies,
    next_move,
)
from krakadyl.core.models import (
    EvidenceRequirement,
    EvidenceState,
    RecoveryWindow,
    RecoveryWindowKind,
    TaskResponsibility,
    TaskStatus,
)

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)


def _requirement(req_id="req-1", recovery_window=None, **resp_kwargs) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        predicate="volatile memory image of host X was preserved",
        acceptable_source_class="forensic acquisition tool",
        recovery_window=recovery_window,
        responsibility=TaskResponsibility(owner="investigator-A", **resp_kwargs),
    )


def _known_window(until, **kwargs) -> RecoveryWindow:
    return RecoveryWindow(kind=RecoveryWindowKind.KNOWN, until=until, **kwargs)


def test_reported_done_alone_is_not_sufficient_evidence():
    req = _requirement(status=TaskStatus.REPORTED_DONE, reported_done_by="investigator-A")
    assert evidence_state_from_requirement(req) == EvidenceState.MISSING


def test_verified_done_with_resolved_flag_is_sufficient():
    req = _requirement(
        status=TaskStatus.VERIFIED_DONE,
        verified_by="investigator-C",
        verification_method="peer-review",
        reported_done_by="investigator-A",
    )
    req.resolved = True
    assert evidence_state_from_requirement(req) == EvidenceState.SUFFICIENT


def test_verified_done_requires_verification_method_not_just_status():
    with pytest.raises(ValidationError):
        TaskResponsibility(owner="investigator-A", status=TaskStatus.VERIFIED_DONE)


def test_verified_done_rejects_self_verification_without_an_automated_check():
    """Independence correction from the Oct 27 review: the same person
    cannot self-verify their own report unless the method is an
    automated, separate-from-the-agent check (prefixed 'tool:')."""
    with pytest.raises(ValidationError):
        TaskResponsibility(
            owner="investigator-A",
            status=TaskStatus.VERIFIED_DONE,
            reported_done_by="investigator-A",
            verified_by="investigator-A",
            verification_method="peer-review",
        )


def test_verified_done_allows_self_triggered_automated_tool_check():
    """An automated checker counts as independent even if the same
    person triggered both the report and the check — the check itself
    is separate code from the self-report, per the Oct 27 correction."""
    resp = TaskResponsibility(
        owner="investigator-A",
        status=TaskStatus.VERIFIED_DONE,
        reported_done_by="investigator-A",
        verified_by="investigator-A",
        verification_method="tool:sha256-checksum-match",
        verified_against="manifest digest matches acquired image",
    )
    assert resp.is_verified


def test_adversarial_scenario_three_investigators_twenty_minutes():
    """The standing acceptance scenario for the whole project: an
    exhausted team, interruptions, a volatile source about to
    disappear, a task reported done that nobody verified, and limited
    authority. KRAKADYL has to keep continuity and propose a legitimate
    action here without fabricating certainty.
    """
    req = _requirement(
        status=TaskStatus.REPORTED_DONE,
        reported_done_by="investigator-A",
        recovery_window=_known_window(
            until=NOW + timedelta(minutes=20),
            what_is_lost_if_missed="the volatile memory image becomes unrecoverable",
        ),
    )

    discrepancies = find_urgent_discrepancies([req], now=NOW)

    assert len(discrepancies) == 1
    assert "investigator-A" in discrepancies[0].reason
    assert discrepancies[0].minutes_left == 20


def test_no_discrepancy_once_independently_verified():
    req = _requirement(
        status=TaskStatus.VERIFIED_DONE,
        reported_done_by="investigator-A",
        verified_by="investigator-C",
        verification_method="peer-review",
        recovery_window=_known_window(
            until=NOW + timedelta(minutes=20),
            what_is_lost_if_missed="the volatile memory image becomes unrecoverable",
        ),
    )
    assert find_urgent_discrepancies([req], now=NOW) == []


def test_not_urgent_when_source_window_is_still_wide_open():
    req = _requirement(
        status=TaskStatus.REPORTED_DONE,
        reported_done_by="investigator-A",
        recovery_window=_known_window(
            until=NOW + timedelta(hours=6),
            what_is_lost_if_missed="the volatile memory image becomes unrecoverable",
        ),
    )
    assert find_urgent_discrepancies([req], now=NOW) == []


def test_conditional_window_is_always_flagged_while_only_claimed():
    """Correction from the Oct 27 review: a window that closes on an
    event (device power-off) with unknown timing must not be silently
    treated as 'not urgent' just because there's no minutes_left to
    compute.
    """
    req = _requirement(
        status=TaskStatus.REPORTED_DONE,
        reported_done_by="investigator-A",
        recovery_window=RecoveryWindow(
            kind=RecoveryWindowKind.CONDITIONAL,
            condition="device is powered off",
            what_is_lost_if_missed="the volatile memory image becomes unrecoverable",
        ),
    )
    discrepancies = find_urgent_discrepancies([req], now=NOW)
    assert len(discrepancies) == 1
    assert discrepancies[0].minutes_left is None
    assert "device is powered off" in discrepancies[0].reason


def test_next_move_picks_the_more_urgent_of_two_open_requirements():
    urgent = _requirement(
        req_id="req-urgent",
        status=TaskStatus.UNASSIGNED,
        recovery_window=_known_window(until=NOW + timedelta(minutes=20), what_is_lost_if_missed="source gone"),
    )
    later = _requirement(
        req_id="req-later",
        status=TaskStatus.UNASSIGNED,
        recovery_window=_known_window(until=NOW + timedelta(hours=6), what_is_lost_if_missed="source gone"),
    )
    result = next_move([urgent, later])
    assert result.primary == "req-urgent"
    assert result.alternatives == ["req-later"]
    assert result.uncertain is False


def test_hypothesis_dependent_count_never_silently_breaks_an_urgency_tie():
    trivial_but_many = _requirement(
        req_id="req-many-trivial",
        status=TaskStatus.UNASSIGNED,
        recovery_window=_known_window(
            until=NOW + timedelta(minutes=20),
            what_is_lost_if_missed="source gone",
            depends_on_hypothesis_ids=["h1", "h2", "h3", "h4", "h5"],
        ),
    )
    decisive_but_one = _requirement(
        req_id="req-one-decisive",
        status=TaskStatus.UNASSIGNED,
        recovery_window=_known_window(
            until=NOW + timedelta(minutes=20),
            what_is_lost_if_missed="source gone",
            depends_on_hypothesis_ids=["h-decisive"],
        ),
    )

    result = next_move([trivial_but_many, decisive_but_one])

    assert result.primary is None
    assert result.uncertain is True
    assert set(result.alternatives) == {"req-many-trivial", "req-one-decisive"}
    assert result.dependents_count == {"req-many-trivial": 5, "req-one-decisive": 1}


def test_dependents_count_deduplicates_repeated_hypothesis_ids():
    req = _requirement(
        status=TaskStatus.UNASSIGNED,
        recovery_window=_known_window(
            until=NOW + timedelta(minutes=20),
            what_is_lost_if_missed="source gone",
            depends_on_hypothesis_ids=["h1", "h1", "h1"],
        ),
    )
    result = next_move([req])
    assert result.dependents_count[req.id] == 1


def test_next_move_reports_uncertain_when_truly_tied_not_a_fabricated_pick():
    same_window = _known_window(until=NOW + timedelta(minutes=20), what_is_lost_if_missed="source gone")
    a = _requirement(req_id="req-a", status=TaskStatus.UNASSIGNED, recovery_window=same_window)
    b = _requirement(req_id="req-b", status=TaskStatus.UNASSIGNED, recovery_window=same_window)

    result = next_move([a, b])

    assert result.primary is None
    assert result.uncertain is True
    assert set(result.alternatives) == {"req-a", "req-b"}


def test_next_move_surfaces_blocked_requirements_without_hiding_them():
    blocked = _requirement(req_id="req-blocked", status=TaskStatus.UNASSIGNED)
    blocked.blocked_by_authority = True
    blocked.blocked_reason = "mandate does not cover this resource"

    result = next_move([blocked])

    assert result.primary is None
    assert result.blocked == [("req-blocked", "mandate does not cover this resource")]


def test_next_move_with_nothing_open_is_not_the_same_as_uncertain():
    resolved = _requirement(
        req_id="req-done",
        status=TaskStatus.VERIFIED_DONE,
        verified_by="investigator-C",
        verification_method="peer-review",
    )
    resolved.resolved = True

    result = next_move([resolved])

    assert result.primary is None
    assert result.uncertain is False
    assert result.alternatives == []


def test_conditional_or_unknown_windows_stay_visible_as_watch_not_buried():
    """A requirement with no known timing must not silently vanish from
    next_move's output just because it can't be time-ranked."""
    timed = _requirement(
        req_id="req-timed",
        status=TaskStatus.UNASSIGNED,
        recovery_window=_known_window(until=NOW + timedelta(hours=1), what_is_lost_if_missed="source gone"),
    )
    conditional = _requirement(
        req_id="req-conditional",
        status=TaskStatus.UNASSIGNED,
        recovery_window=RecoveryWindow(
            kind=RecoveryWindowKind.CONDITIONAL,
            condition="log rotation",
            what_is_lost_if_missed="log entries overwritten",
        ),
    )

    result = next_move([timed, conditional])

    assert result.primary == "req-timed"
    assert result.conditional_watch == ["req-conditional"]
    assert "req-conditional" not in result.alternatives
