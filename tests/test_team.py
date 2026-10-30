"""Level 4 core: teammates' statements as append-only records; conflicts
derived from them; the narrow set of requirement transitions they allow."""

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from krakadyl.core.acquisition import requirement_revision_digest
from krakadyl.core.continuity import evidence_state_from_requirement, find_urgent_discrepancies
from krakadyl.core.models import (
    EvidenceRequirement,
    EvidenceState,
    RecoveryWindow,
    RecoveryWindowKind,
    TaskResponsibility,
    TaskStatus,
)
from krakadyl.core.team import (
    BLAME_TERMS,
    ClaimKind,
    ConflictKind,
    EvidenceRef,
    TeamRejected,
    conflicted_requirement_ids,
    find_conflicts,
    list_team_records,
    record_team_statement,
)
from krakadyl.store import KrakadylStore

NOW = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)
CASE, REQ = "case-001", "req-memory-image"


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class _Refs:
    """Stands in for the API's store/file-backed reference check."""

    def __init__(self):
        self.current = {"obs-mem-1": _digest("image one"), "obs-mem-2": _digest("image two")}

    def ref(self, ref_id):
        return EvidenceRef(kind="observation", ref_id=ref_id, digest=self.current[ref_id])

    def __call__(self, ref):
        if ref.ref_id not in self.current:
            return "no such observation"
        if self.current[ref.ref_id] != ref.digest:
            return "digest differs from the recorded observation"
        return None


@pytest.fixture
def case(tmp_path):
    store = KrakadylStore(tmp_path / "team.db")
    store.put(CASE, "requirement", EvidenceRequirement(
        id=REQ,
        predicate="the volatile memory image of device-A is preserved",
        acceptable_source_class="forensic acquisition tool",
        recovery_window=RecoveryWindow(
            kind=RecoveryWindowKind.KNOWN, until=NOW + timedelta(minutes=20),
            what_is_lost_if_missed="the memory image becomes unrecoverable",
        ),
        responsibility=TaskResponsibility(owner="investigator-A", status=TaskStatus.ASSIGNED),
    ), NOW.isoformat())
    yield store, _Refs()
    store.close()


def _req(store):
    return store.get(CASE, "requirement", REQ, EvidenceRequirement)


def _say(store, refs, actor, kind, statement="statement", **kwargs):
    return record_team_statement(
        store, case_id=CASE, requirement_id=REQ, kind=kind, actor=actor, statement=statement,
        expected_requirement_revision=kwargs.pop("revision", requirement_revision_digest(_req(store))),
        check_ref=refs, now=kwargs.pop("now", NOW), **kwargs,
    )


def _open(store, refs):
    return find_conflicts(REQ, list_team_records(store, CASE), refs)[0]


def test_teammate_claim_is_a_claim_until_someone_else_verifies_it(case):
    store, refs = case
    claim, after = _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE,
                        "memory image preserved to the evidence share", evidence_refs=(refs.ref("obs-mem-1"),))
    assert after.responsibility.status == TaskStatus.REPORTED_DONE
    assert after.responsibility.reported_done_by == "investigator-B"
    assert evidence_state_from_requirement(after) == EvidenceState.MISSING
    assert [d.requirement_id for d in find_urgent_discrepancies([after], NOW)] == [REQ]

    with pytest.raises(TeamRejected, match="someone other than the claimant"):
        _say(store, refs, "investigator-B", ClaimKind.VERIFIED, refers_to=(claim.record_id,),
             verification_method="re-hashed the share copy")

    _, verified = _say(store, refs, "investigator-C", ClaimKind.VERIFIED, "hash matches the share copy",
                       refers_to=(claim.record_id,), verification_method="re-hashed the share copy")
    assert verified.resolved is True
    assert verified.responsibility.verified_by == "investigator-C"
    assert claim.record_id in verified.responsibility.verified_against
    assert evidence_state_from_requirement(verified) == EvidenceState.SUFFICIENT


def test_only_the_owner_acknowledges_and_only_from_assigned(case):
    store, refs = case
    with pytest.raises(TeamRejected, match="only the owner"):
        _say(store, refs, "investigator-B", ClaimKind.ACKNOWLEDGED)
    _, after = _say(store, refs, "investigator-A", ClaimKind.ACKNOWLEDGED)
    assert after.responsibility.status == TaskStatus.ACKNOWLEDGED
    assert after.responsibility.accepted_by == "investigator-A"
    with pytest.raises(TeamRejected, match="not 'assigned'"):
        _say(store, refs, "investigator-A", ClaimKind.ACKNOWLEDGED)


def test_a_person_cannot_label_their_check_as_automated(case):
    store, refs = case
    claim, _ = _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE)
    with pytest.raises(TeamRejected, match="reserved for automated"):
        _say(store, refs, "investigator-C", ClaimKind.VERIFIED, refers_to=(claim.record_id,),
             verification_method="tool:sha256")


def test_the_first_claimant_stays_on_record_and_cannot_verify_a_later_claim(case):
    store, refs = case
    _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE)
    second, after = _say(store, refs, "investigator-D", ClaimKind.REPORTED_DONE)
    assert after.responsibility.reported_done_by == "investigator-B"
    with pytest.raises(TeamRejected, match="someone other than the claimant"):
        _say(store, refs, "investigator-B", ClaimKind.VERIFIED, refers_to=(second.record_id,),
             verification_method="looked at it")


def test_competing_completions_block_verification_until_a_non_party_resolves(case):
    store, refs = case
    first, _ = _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, evidence_refs=(refs.ref("obs-mem-1"),))
    _say(store, refs, "investigator-D", ClaimKind.REPORTED_DONE, evidence_refs=(refs.ref("obs-mem-2"),))
    [conflict] = _open(store, refs)
    assert conflict.kind == ConflictKind.COMPETING_COMPLETION
    assert conflict.parties == ("investigator-B", "investigator-D")
    assert conflicted_requirement_ids([REQ], list_team_records(store, CASE), refs) == {REQ}

    with pytest.raises(TeamRejected, match="open conflict"):
        _say(store, refs, "investigator-C", ClaimKind.VERIFIED, refers_to=(first.record_id,), verification_method="m")
    with pytest.raises(TeamRejected, match="not a party"):
        _say(store, refs, "investigator-B", ClaimKind.RESOLUTION, refers_to=conflict.record_ids,
             resolves_conflict_id=conflict.conflict_id, decision="keep_current_state")
    with pytest.raises(TeamRejected, match="exactly the records"):
        _say(store, refs, "investigator-C", ClaimKind.RESOLUTION, refers_to=(first.record_id,),
             resolves_conflict_id=conflict.conflict_id, decision="keep_current_state")

    _say(store, refs, "investigator-C", ClaimKind.RESOLUTION, "obs-mem-1 is the full image; obs-mem-2 is partial",
         refers_to=conflict.record_ids, resolves_conflict_id=conflict.conflict_id, decision="keep_current_state")
    assert _open(store, refs) == []
    _, verified = _say(store, refs, "investigator-C", ClaimKind.VERIFIED, refers_to=(first.record_id,),
                       verification_method="re-hashed obs-mem-1")
    assert verified.resolved is True


def test_dispute_after_verification_surfaces_and_reopening_keeps_history(case):
    store, refs = case
    claim, _ = _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE)
    verification, verified = _say(store, refs, "investigator-C", ClaimKind.VERIFIED,
                                  refers_to=(claim.record_id,), verification_method="peer review")
    assert verified.resolved
    _say(store, refs, "investigator-D", ClaimKind.DISPUTED, "the share copy is 0 bytes",
         refers_to=(verification.record_id,))
    [conflict] = _open(store, refs)
    assert conflict.kind == ConflictKind.DISPUTED
    assert conflicted_requirement_ids([REQ], list_team_records(store, CASE), refs) == {REQ}

    _, reopened = _say(store, refs, "investigator-E", ClaimKind.RESOLUTION, "confirmed 0-byte copy",
                       refers_to=conflict.record_ids, resolves_conflict_id=conflict.conflict_id,
                       decision="reopen_requirement")
    assert reopened.resolved is False
    assert reopened.responsibility.status == TaskStatus.UNKNOWN
    assert reopened.responsibility.verified_by is None
    kinds = [r.kind for r in list_team_records(store, CASE)]
    assert kinds == [ClaimKind.REPORTED_DONE, ClaimKind.VERIFIED, ClaimKind.DISPUTED, ClaimKind.RESOLUTION]


def test_evidence_that_stops_matching_becomes_a_conflict_that_cannot_be_kept(case):
    store, refs = case
    _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, evidence_refs=(refs.ref("obs-mem-1"),))
    assert _open(store, refs) == []
    refs.current["obs-mem-1"] = _digest("replaced")
    [conflict] = _open(store, refs)
    assert conflict.kind == ConflictKind.EVIDENCE_MISMATCH
    with pytest.raises(TeamRejected, match="cannot be kept"):
        _say(store, refs, "investigator-C", ClaimKind.RESOLUTION, refers_to=conflict.record_ids,
             resolves_conflict_id=conflict.conflict_id, decision="keep_current_state")
    _, reopened = _say(store, refs, "investigator-C", ClaimKind.RESOLUTION, refers_to=conflict.record_ids,
                       resolves_conflict_id=conflict.conflict_id, decision="reopen_requirement")
    assert reopened.responsibility.status == TaskStatus.UNKNOWN


def test_blocked_and_done_from_different_people_contradict(case):
    store, refs = case
    _, blocked = _say(store, refs, "investigator-A", ClaimKind.BLOCKED, "no write blocker available")
    assert blocked.responsibility.status == TaskStatus.BLOCKED
    _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, "imaged it with my kit")
    [conflict] = _open(store, refs)
    assert conflict.kind == ConflictKind.STATUS_CONTRADICTION


def test_non_owner_blocked_is_recorded_without_changing_status(case):
    store, refs = case
    _, after = _say(store, refs, "investigator-B", ClaimKind.BLOCKED, "cannot reach the device")
    assert after.responsibility.status == TaskStatus.ASSIGNED
    assert len(list_team_records(store, CASE)) == 1


def test_stale_revision_and_broken_evidence_are_refused_without_writing(case):
    store, refs = case
    with pytest.raises(TeamRejected, match="changed since"):
        _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, revision="0" * 64)
    bad = EvidenceRef(kind="observation", ref_id="obs-mem-1", digest=_digest("something else"))
    with pytest.raises(TeamRejected, match="cannot be used"):
        _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, evidence_refs=(bad,))
    assert list_team_records(store, CASE) == []
    assert _req(store).responsibility.status == TaskStatus.ASSIGNED


def test_records_are_append_only_in_the_database(case):
    store, refs = case
    _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.atomic_write(lambda c: c.execute("UPDATE team_records SET actor='investigator-Z'"))


def test_conflict_descriptions_describe_the_case_not_people(case):
    store, refs = case
    first, _ = _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, evidence_refs=(refs.ref("obs-mem-1"),))
    _say(store, refs, "investigator-D", ClaimKind.REPORTED_DONE, evidence_refs=(refs.ref("obs-mem-2"),))
    _say(store, refs, "investigator-A", ClaimKind.BLOCKED)
    _say(store, refs, "investigator-E", ClaimKind.DISPUTED, refers_to=(first.record_id,))
    refs.current["obs-mem-2"] = _digest("changed")
    conflicts = _open(store, refs)
    assert {c.kind for c in conflicts} == set(ConflictKind)
    for conflict in conflicts:
        text = conflict.description.lower()
        assert not [term for term in BLAME_TERMS if term in text], text
        assert "investigator-" not in text  # parties are data, not narration


def test_a_verification_that_predates_team_records_can_still_be_disputed(case):
    store, refs = case
    store.put(CASE, "requirement", EvidenceRequirement(**{**_req(store).model_dump(), "resolved": True,
        "responsibility": TaskResponsibility(owner="investigator-A", status=TaskStatus.VERIFIED_DONE,
            reported_done_by="investigator-A", verified_by="investigator-C",
            verification_method="peer-review").model_dump()}), NOW.isoformat())
    _say(store, refs, "investigator-D", ClaimKind.DISPUTED, "the image on the share is truncated")
    [conflict] = _open(store, refs)
    assert conflict.kind == ConflictKind.DISPUTED and conflict.parties == ("investigator-D",)
    with pytest.raises(TeamRejected, match="not a party"):
        _say(store, refs, "investigator-C", ClaimKind.RESOLUTION, refers_to=conflict.record_ids,
             resolves_conflict_id=conflict.conflict_id, decision="keep_current_state")
    _, reopened = _say(store, refs, "investigator-E", ClaimKind.RESOLUTION, refers_to=conflict.record_ids,
                       resolves_conflict_id=conflict.conflict_id, decision="reopen_requirement")
    assert reopened.resolved is False and reopened.responsibility.status == TaskStatus.UNKNOWN


def test_nothing_to_dispute_on_an_open_requirement(case):
    store, refs = case
    with pytest.raises(TeamRejected, match="nothing|no recorded"):
        _say(store, refs, "investigator-D", ClaimKind.DISPUTED, "not done")
