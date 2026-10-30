"""Level 5: counterfactuals are measured with the real pipeline on copies,
never touch the case, and never become executable."""

import sqlite3
from datetime import timedelta

import pytest

from krakadyl.core.counterfactual import (
    CaseInputs,
    CounterfactualRejected,
    Delta,
    DeltaKind,
    MAX_COUNTERFACTUALS_PER_CASE,
    Question,
    base_state_digest,
    evaluate_counterfactual,
    list_counterfactuals,
    save_counterfactual,
)
from krakadyl.core.models import AuthorityVerdict, EvidenceRequirement, TaskResponsibility, TaskStatus
from krakadyl.store import KrakadylStore
from test_executor import NOW, _mandate, _verified_requirement, two_device_case  # noqa: F401

WHEN = NOW
EXPORT_A = Question(allowed_device="device-A", destination="reviewer-authorized")
EXPORT_B = Question(allowed_device="device-B", destination="reviewer-authorized")


def _unverified(req_id, obs_id):
    return EvidenceRequirement(
        id=req_id, predicate=f"{obs_id} acquired per procedure", acceptable_source_class="x", observation_id=obs_id,
        responsibility=TaskResponsibility(owner="investigator-A", status=TaskStatus.REPORTED_DONE,
                                          reported_done_by="investigator-A"),
    )


def _inputs(case, *, requirements=None, mandate=None, conflicted=frozenset(), resolvable=frozenset()):
    observations, files, reqs = case
    return CaseInputs(case_id="case-001", mandate=mandate or _mandate(), observations=observations,
                      requirements=requirements if requirements is not None else reqs, observation_files=files,
                      conflicted_requirement_ids=conflicted, resolvable_requirement_ids=resolvable)


def _eval(inputs, question, *deltas):
    return evaluate_counterfactual(inputs, question, tuple(deltas), created_by="investigator-C", now=WHEN)


def test_out_of_mandate_device_needs_a_resource_grant_and_says_so(two_device_case):
    cf = _eval(_inputs(two_device_case), EXPORT_B, Delta(kind=DeltaKind.GRANT_RESOURCE, value="case-001/device-B"))
    assert cf.hypothetical is True and cf.counterfactual_id.startswith("cf-")
    assert cf.real.verdict == AuthorityVerdict.FORBIDDEN
    # obs-b1 has no governing requirement, so even a wider mandate does not make it exportable.
    assert cf.hypothetical_outcome.verdict == AuthorityVerdict.FORBIDDEN
    assert cf.hypothetical_outcome.authority_state.value == "granted"
    assert "no EvidenceRequirement governs" in cf.hypothetical_outcome.reasons[-1]
    assert cf.verdict_changed is False


def test_unverified_gap_measures_which_assumption_matters(two_device_case):
    reqs = [_verified_requirement("req-a1", "obs-a1"), _unverified("req-a2", "obs-a2")]
    cf = _eval(_inputs(two_device_case, requirements=reqs), EXPORT_A,
               Delta(kind=DeltaKind.REQUIREMENT_VERIFIED, requirement_id="req-a2"),
               Delta(kind=DeltaKind.GRANT_DESTINATION, value="court-registry"))
    assert cf.real.verdict == AuthorityVerdict.FORBIDDEN
    assert cf.hypothetical_outcome.verdict == AuthorityVerdict.ALLOWED
    assert cf.hypothetical_outcome.would_include == ("obs-a1", "obs-a2")
    effects = {e.delta.kind: e for e in cf.effects}
    assert effects[DeltaKind.REQUIREMENT_VERIFIED].necessary and effects[DeltaKind.REQUIREMENT_VERIFIED].sufficient_alone
    assert not effects[DeltaKind.GRANT_DESTINATION].necessary and not effects[DeltaKind.GRANT_DESTINATION].sufficient_alone


def test_a_source_turns_forbidden_into_gather_evidence(two_device_case):
    reqs = [_verified_requirement("req-a1", "obs-a1"), _unverified("req-a2", "obs-a2")]
    cf = _eval(_inputs(two_device_case, requirements=reqs), EXPORT_A,
               Delta(kind=DeltaKind.SOURCE_AVAILABLE, requirement_id="req-a2"))
    assert (cf.real.verdict, cf.hypothetical_outcome.verdict) == (AuthorityVerdict.FORBIDDEN, AuthorityVerdict.GATHER_EVIDENCE)


def test_resolving_a_conflict_hypothetically(two_device_case):
    cf = _eval(_inputs(two_device_case, conflicted=frozenset({"req-a1"})), EXPORT_A,
               Delta(kind=DeltaKind.CONFLICT_RESOLVED, requirement_id="req-a1"))
    assert (cf.real.verdict, cf.hypothetical_outcome.verdict) == (AuthorityVerdict.FORBIDDEN, AuthorityVerdict.ALLOWED)


def test_revoked_and_expired_mandates(two_device_case):
    revoked = _mandate(revoked=True, revoked_reason="reassigned", revision="2")
    cf = _eval(_inputs(two_device_case, mandate=revoked), EXPORT_A, Delta(kind=DeltaKind.MANDATE_NOT_REVOKED))
    assert cf.hypothetical_outcome.verdict == AuthorityVerdict.ALLOWED
    expired = _mandate(valid_until=WHEN - timedelta(hours=1))
    cf = _eval(_inputs(two_device_case, mandate=expired), EXPORT_A,
               Delta(kind=DeltaKind.EXTEND_MANDATE_UNTIL, until=WHEN + timedelta(days=1)))
    assert (cf.real.verdict, cf.hypothetical_outcome.verdict) == (AuthorityVerdict.FORBIDDEN, AuthorityVerdict.ALLOWED)


def test_tampered_bytes_cannot_be_assumed_intact(two_device_case):
    observations, files, _ = two_device_case
    files["obs-a1"].write_bytes(b"tampered")
    every_kind = [
        Delta(kind=DeltaKind.REQUIREMENT_VERIFIED, requirement_id="req-a1"),
        Delta(kind=DeltaKind.CONFLICT_RESOLVED, requirement_id="req-a1"),
        Delta(kind=DeltaKind.SOURCE_AVAILABLE, requirement_id="req-a1"),
        Delta(kind=DeltaKind.MANDATE_NOT_REVOKED),
    ]
    cf = _eval(_inputs(two_device_case), EXPORT_A, *every_kind)
    assert cf.hypothetical_outcome.verdict == AuthorityVerdict.FORBIDDEN
    assert "integrity check failed" in " ".join(cf.hypothetical_outcome.reasons)


def test_inputs_are_never_mutated(two_device_case):
    inputs = _inputs(two_device_case)
    before = inputs.model_dump()
    question = EXPORT_B
    digest = base_state_digest(inputs, question)
    _eval(inputs, question, Delta(kind=DeltaKind.GRANT_RESOURCE, value="case-001/device-B"),
          Delta(kind=DeltaKind.REQUIREMENT_UNRESOLVABLE, requirement_id="req-a1"))
    assert inputs.model_dump() == before
    assert base_state_digest(inputs, question) == digest


@pytest.mark.parametrize("deltas, match", [
    ((), "at least one"),
    ((Delta(kind=DeltaKind.REQUIREMENT_VERIFIED, requirement_id="nope"),), "no requirement"),
    ((Delta(kind=DeltaKind.REQUIREMENT_VERIFIED, requirement_id="req-a1"),
      Delta(kind=DeltaKind.REQUIREMENT_UNRESOLVABLE, requirement_id="req-a1")), "both"),
    (tuple(Delta(kind=DeltaKind.GRANT_DESTINATION, value=f"d{i}") for i in range(9)), "at most"),
])
def test_malformed_counterfactuals_are_refused(two_device_case, deltas, match):
    with pytest.raises(CounterfactualRejected, match=match):
        _eval(_inputs(two_device_case), EXPORT_A, *deltas)


@pytest.mark.parametrize("kwargs", [
    {"kind": DeltaKind.GRANT_RESOURCE},
    {"kind": DeltaKind.MANDATE_NOT_REVOKED, "value": "x"},
    {"kind": DeltaKind.REQUIREMENT_VERIFIED, "value": "x"},
    {"kind": DeltaKind.EXTEND_MANDATE_UNTIL, "until": NOW.replace(tzinfo=None)},
])
def test_delta_shape_is_enforced(kwargs):
    with pytest.raises(ValueError):
        Delta(**kwargs)


def test_stored_apart_from_case_state_and_append_only(two_device_case, tmp_path):
    store = KrakadylStore(tmp_path / "cf.db")
    cf = _eval(_inputs(two_device_case), EXPORT_B, Delta(kind=DeltaKind.GRANT_RESOURCE, value="case-001/device-B"))
    save_counterfactual(store, cf)
    assert list_counterfactuals(store, "case-001") == [cf]
    assert store.read_locked(lambda c: c.execute("SELECT COUNT(*) FROM objects").fetchone()[0]) == 0
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.atomic_write(lambda c: c.execute("UPDATE counterfactuals SET created_by='someone'"))
    store.close()


def test_counterfactuals_are_bounded_per_case(two_device_case, tmp_path):
    store = KrakadylStore(tmp_path / "cf-limit.db")
    cf = _eval(_inputs(two_device_case), EXPORT_B, Delta(kind=DeltaKind.GRANT_RESOURCE, value="case-001/device-B"))
    for index in range(MAX_COUNTERFACTUALS_PER_CASE):
        save_counterfactual(store, cf.model_copy(update={"counterfactual_id": f"cf-{index:08d}"}))
    with pytest.raises(CounterfactualRejected, match="reached the limit"):
        save_counterfactual(store, cf.model_copy(update={"counterfactual_id": "cf-over-limit"}))
    store.close()
