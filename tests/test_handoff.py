"""Level 4: open team conflicts reach the policy engine, and a shift
handoff is answerable from recorded state alone."""

from datetime import timedelta

import pytest

from krakadyl.core.acquisition import requirement_revision_digest
from krakadyl.core.executor import prepare_evidence_package, propose_recovery_route
from krakadyl.core.handoff import (
    HandoffRejected,
    InFlightAcquisition,
    accept_handoff,
    build_shift_handoff,
    handoff_text_lines,
    list_shift_events,
    record_handoff,
)
from krakadyl.core.models import (
    AuthorityVerdict,
    EvidenceRequirement,
    Hypothesis,
    TaskResponsibility,
    TaskStatus,
)
from krakadyl.core.team import BLAME_TERMS, ClaimKind, list_team_records
from test_executor import _mandate, _proposed_action, _verified_requirement, two_device_case  # noqa: F401
from test_team import CASE, NOW, REQ, _Refs, _say, case  # noqa: F401

IDENTITIES = {"investigator-A", "investigator-B", "investigator-C", "investigator-D", "investigator-E"}


# --- policy wiring ---

def _prepare(two_device_case, conflicted, **kwargs):
    observations, files, requirements = two_device_case
    return prepare_evidence_package(
        proposed_action=_proposed_action(), mandate=_mandate(), observations=observations,
        requirements=requirements, observation_files=files, allowed_device="device-A",
        destination="reviewer-authorized", now=NOW - timedelta(days=3), conflicted_requirement_ids=conflicted,
        **kwargs,
    )


def test_an_open_conflict_makes_verified_evidence_conflicting(two_device_case):
    decision, prepared = _prepare(two_device_case, frozenset({"req-a1"}))
    assert decision.verdict == AuthorityVerdict.FORBIDDEN
    assert decision.evidence_state.value == "conflicting"
    assert "open team conflict" in decision.reasons[-1]
    assert prepared is None


def test_without_conflicts_the_same_case_is_still_allowed(two_device_case):
    decision, _ = _prepare(two_device_case, frozenset())
    assert decision.verdict == AuthorityVerdict.ALLOWED


def test_a_conflict_raised_after_prepare_blocks_execution(two_device_case, tmp_path):
    observations, files, requirements = two_device_case
    decision, prepared = _prepare(two_device_case, frozenset())
    from krakadyl.core.executor import execute_prepared_action

    receipt = execute_prepared_action(
        prepared=prepared, decision=decision, proposed_action=_proposed_action(), observations=observations,
        requirements=requirements, observation_files=files, current_mandate=_mandate(), consumed_nonces=set(),
        out_dir=tmp_path / "pkg", now=NOW - timedelta(days=3), conflicted_requirement_ids=frozenset({"req-a2"}),
    )
    assert receipt.executed is False
    assert not (tmp_path / "pkg").exists()


def test_recovery_can_exclude_the_contested_item_and_says_why(two_device_case):
    observations, files, requirements = two_device_case
    outcome = propose_recovery_route(
        proposed_action=_proposed_action(), mandate=_mandate(), observations=observations,
        requirements=requirements, observation_files=files, allowed_device="device-A",
        destination="reviewer-authorized", now=NOW - timedelta(days=3),
        conflicted_requirement_ids=frozenset({"req-a2"}),
    )
    assert outcome.excluded_resources == ["obs-a2"]
    assert outcome.recovered_prepared is not None
    reasons = {e.resource_id: e.reason for e in outcome.recovered_prepared.excluded_resource_reasons}
    assert "open team conflict" in reasons["obs-a2"]


# --- handoff ---

def _view(store, refs, acquisitions=()):
    return build_shift_handoff(
        case_id=CASE, requirements=store.list(CASE, "requirement", EvidenceRequirement),
        hypotheses=store.list(CASE, "hypothesis", Hypothesis), records=list_team_records(store, CASE),
        check_ref=refs, acquisitions=list(acquisitions), now=NOW,
    )


def _add_requirement(store, req_id, status=TaskStatus.ASSIGNED, owner="investigator-A"):
    store.put(CASE, "requirement", EvidenceRequirement(
        id=req_id, predicate=f"{req_id} predicate", acceptable_source_class="x",
        responsibility=TaskResponsibility(owner=owner, status=status),
    ), NOW.isoformat())


def test_handoff_puts_conflicts_and_expiring_claims_first(case):
    store, refs = case
    claim, _ = _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, evidence_refs=(refs.ref("obs-mem-1"),))
    _say(store, refs, "investigator-D", ClaimKind.REPORTED_DONE, evidence_refs=(refs.ref("obs-mem-2"),))
    _add_requirement(store, "req-unacked")
    store.put(CASE, "hypothesis", Hypothesis(id="hyp-9", explanation="x", discriminating_requirement_id=REQ),
              NOW.isoformat())
    view = _view(store, refs, [InFlightAcquisition(workflow_id="wf-1", requirement_id="req-x", state="unknown"),
                               InFlightAcquisition(workflow_id="wf-2", requirement_id="req-y", state="completed")])

    assert [c.kind.value for c in view.open_conflicts] == ["competing_completion"]
    assert [i.requirement_id for i in view.urgent_unverified] == [REQ]
    assert claim.record_id in view.urgent_unverified[0].provenance
    assert view.urgent_unverified[0].minutes_left == 20
    assert [i.requirement_id for i in view.not_acknowledged] == ["req-unacked"]
    assert [a.workflow_id for a in view.acquisitions_in_flight] == ["wf-1"]
    assert view.hypotheses_needing_review[0][0] == "hyp-9"


def test_handoff_language_describes_the_case_not_people(case):
    store, refs = case
    _say(store, refs, "investigator-A", ClaimKind.BLOCKED, "no write blocker")
    _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, evidence_refs=(refs.ref("obs-mem-1"),))
    _add_requirement(store, "req-unacked")
    for line in handoff_text_lines(_view(store, refs)):
        assert not [t for t in BLAME_TERMS if t in line.lower()], line


def test_state_digest_is_stable_and_moves_with_the_case(case):
    store, refs = case
    first = _view(store, refs)
    assert _view(store, refs).state_digest == first.state_digest
    _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE)
    assert _view(store, refs).state_digest != first.state_digest


def _handoff(store, refs, **kwargs):
    view = _view(store, refs)
    values = dict(case_id=CASE, from_actor="investigator-A", to_actor="investigator-E",
                  known_identities=IDENTITIES, seen_state_digest=view.state_digest, current=view,
                  transfer_requirement_ids=(REQ,), note="memory image still pending", now=NOW)
    values.update(kwargs)
    return record_handoff(store, **values)


def test_accepting_a_handoff_transfers_ownership_but_never_authority(case):
    store, refs = case
    handoff = _handoff(store, refs)
    with pytest.raises(HandoffRejected, match="addressed to investigator-E"):
        accept_handoff(store, case_id=CASE, handoff_id=handoff.event_id, actor="investigator-B",
                       current=_view(store, refs), now=NOW)
    accepted = accept_handoff(store, case_id=CASE, handoff_id=handoff.event_id, actor="investigator-E",
                              current=_view(store, refs), now=NOW)
    assert accepted.transferred == (REQ,) and accepted.state_changed_since_handoff is False
    requirement = store.get(CASE, "requirement", REQ, EvidenceRequirement)
    assert requirement.responsibility.owner == "investigator-E"
    assert requirement.responsibility.status == TaskStatus.ACKNOWLEDGED
    assert [e.kind for e in list_shift_events(store, CASE)] == ["handoff", "accepted"]
    with pytest.raises(HandoffRejected, match="already accepted"):
        accept_handoff(store, case_id=CASE, handoff_id=handoff.event_id, actor="investigator-E",
                       current=_view(store, refs), now=NOW)


def test_a_requirement_that_moved_after_the_handoff_is_not_handed_over_blind(case):
    store, refs = case
    handoff = _handoff(store, refs)
    _say(store, refs, "investigator-B", ClaimKind.REPORTED_DONE, "done meanwhile")
    accepted = accept_handoff(store, case_id=CASE, handoff_id=handoff.event_id, actor="investigator-E",
                              current=_view(store, refs), now=NOW)
    assert accepted.transferred == ()
    assert accepted.not_transferred[0][0] == REQ
    assert accepted.state_changed_since_handoff is True
    assert store.get(CASE, "requirement", REQ, EvidenceRequirement).responsibility.owner == "investigator-A"


def test_acceptance_detects_unrelated_state_change_after_handoff(case):
    store, refs = case
    unrelated = "req-unrelated"
    _add_requirement(store, unrelated)
    handoff_view = _view(store, refs)
    handoff = _handoff(store, refs)

    changed = EvidenceRequirement(
        **{
            **store.get(CASE, "requirement", unrelated, EvidenceRequirement).model_dump(),
            "responsibility": TaskResponsibility(owner="investigator-A", status=TaskStatus.BLOCKED).model_dump(),
        }
    )
    store.put(CASE, "requirement", changed, NOW.isoformat())

    accepted = accept_handoff(
        store, case_id=CASE, handoff_id=handoff.event_id, actor="investigator-E",
        current=handoff_view, now=NOW,
    )
    assert accepted.state_changed_since_handoff is True


@pytest.mark.parametrize("kwargs, match", [
    ({"to_actor": "investigator-A"}, "someone else"),
    ({"to_actor": "stranger"}, "not a configured operator"),
    ({"seen_state_digest": "0" * 64}, "changed since"),
    ({"from_actor": "investigator-B"}, "owned by investigator-A"),
])
def test_handoff_refusals(case, kwargs, match):
    store, refs = case
    with pytest.raises(HandoffRejected, match=match):
        _handoff(store, refs, **kwargs)
    assert list_shift_events(store, CASE) == []


def test_reported_done_claim_keeps_its_status_when_ownership_moves(case):
    store, refs = case
    _say(store, refs, "investigator-A", ClaimKind.REPORTED_DONE, "imaged")
    handoff = _handoff(store, refs)
    accept_handoff(store, case_id=CASE, handoff_id=handoff.event_id, actor="investigator-E",
                   current=_view(store, refs), now=NOW)
    requirement = store.get(CASE, "requirement", REQ, EvidenceRequirement)
    assert requirement.responsibility.status == TaskStatus.REPORTED_DONE
    assert requirement.responsibility.reported_done_by == "investigator-A"
    assert requirement_revision_digest(requirement)  # still a valid, digestible requirement
