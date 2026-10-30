"""Red team of Level 4 shared custody (docs/red-team-level4-shared-custody.md).

Each test reproduces one finding against commit 7c64649 and was observed
failing before its fix."""

import pytest

from krakadyl.core.acquisition import requirement_revision_digest
from krakadyl.core.handoff import accept_handoff
from krakadyl.core.models import EvidenceRequirement, TaskStatus
from krakadyl.core.team import ClaimKind, TeamRejected, find_conflicts, list_team_records
from test_handoff import _handoff, _view  # noqa: F401
from test_team import CASE, NOW, REQ, _open, _req, _say, case  # noqa: F401


def _reopen_after_dispute(store, refs):
    claim, _ = _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, "imaged it")
    verification, _ = _say(store, refs, "investigator-C", ClaimKind.VERIFIED, refers_to=(claim.record_id,),
                           verification_method="peer review")
    _say(store, refs, "investigator-D", ClaimKind.DISPUTED, "0-byte file", refers_to=(verification.record_id,))
    [conflict] = _open(store, refs)
    _say(store, refs, "investigator-E", ClaimKind.RESOLUTION, "confirmed 0 bytes", refers_to=conflict.record_ids,
         resolves_conflict_id=conflict.conflict_id, decision="reopen_requirement")
    return claim


# F1 — a reopen discards the state it was about; the claim that produced
# that state cannot simply be verified again.
def test_a_claim_superseded_by_a_reopen_cannot_be_verified_again(case):
    store, refs = case
    old_claim = _reopen_after_dispute(store, refs)
    with pytest.raises(TeamRejected, match="before the requirement was reopened"):
        _say(store, refs, "investigator-F", ClaimKind.VERIFIED, refers_to=(old_claim.record_id,),
             verification_method="looked again")
    assert _req(store).resolved is False
    fresh, _ = _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, "re-imaged, 4 GiB")
    _, verified = _say(store, refs, "investigator-F", ClaimKind.VERIFIED, refers_to=(fresh.record_id,),
                       verification_method="re-hashed")
    assert verified.resolved is True


# F1b — disagreements about the discarded state do not haunt the new one.
def test_records_before_a_reopen_do_not_form_new_conflicts(case):
    store, refs = case
    _reopen_after_dispute(store, refs)
    _say(store, refs, "investigator-A", ClaimKind.BLOCKED, "need a new write blocker")
    # B's pre-reopen 'done' must not contradict A's post-reopen 'blocked'.
    assert _open(store, refs) == []


# F2 — accepting a handoff must not turn 'blocked' or 'unknown' into
# 'acknowledged': that would erase exactly the uncertainty being handed over.
@pytest.mark.parametrize("setup, expected", [
    ("blocked", TaskStatus.BLOCKED),
    ("unknown", TaskStatus.UNKNOWN),
])
def test_handoff_keeps_blocked_and_unknown_status(case, setup, expected):
    store, refs = case
    if setup == "blocked":
        _say(store, refs, "investigator-A", ClaimKind.BLOCKED, "no write blocker")
    else:
        _reopen_after_dispute(store, refs)
    handoff = _handoff(store, refs)
    accept_handoff(store, case_id=CASE, handoff_id=handoff.event_id, actor="investigator-E",
                   current=_view(store, refs), now=NOW)
    requirement = _req(store)
    assert requirement.responsibility.owner == "investigator-E"
    assert requirement.responsibility.status == expected


# F3 — resolving a conflict by reopening must not silently undo an
# owner's explicit "this evidence is not obtainable".
def test_reopen_does_not_clear_an_abstention(case):
    store, refs = case
    claim, _ = _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, "imaged it")
    _say(store, refs, "investigator-D", ClaimKind.DISPUTED, "nothing on the share", refers_to=(claim.record_id,))
    closed = EvidenceRequirement(**{**_req(store).model_dump(), "unresolvable": True,
                                    "unresolvable_reason": "device wiped — closed by investigator-A"})
    store.put(CASE, "requirement", closed, NOW.isoformat())
    [conflict] = _open(store, refs)
    _, after = _say(store, refs, "investigator-E", ClaimKind.RESOLUTION, "B's copy is empty",
                    refers_to=conflict.record_ids, resolves_conflict_id=conflict.conflict_id,
                    decision="reopen_requirement")
    assert after.unresolvable is True
    assert after.unresolvable_reason == "device wiped — closed by investigator-A"
    assert after.responsibility.status == TaskStatus.UNKNOWN
