"""Level 3 wiring: when does an open requirement have an authorized,
discriminating capture route, and does the executor's GATHER_EVIDENCE
verdict follow from that route — and only from it?
"""

from datetime import timedelta

import pytest

from krakadyl.core.acquisition_routes import (
    AcquisitionRoute,
    RouteRefusal,
    SourceCapability,
    acquisition_route,
    need_snapshot_for,
    resolvable_requirement_ids,
)
from krakadyl.core.acquisition_store import SQLiteAcquisitionGate
from krakadyl.core.executor import prepare_evidence_package
from krakadyl.core.models import (
    AuthorityVerdict,
    EvidenceRequirement,
    Hypothesis,
    Mandate,
    TaskResponsibility,
    TaskStatus,
)
from test_executor import NOW, _mandate, _proposed_action, _verified_requirement, two_device_case  # noqa: F401

SOURCE = SourceCapability(
    source_id="operator-intake",
    capability_version="operator-intake-v1",
    source_class="operator photograph",
    description="An authorized investigator photographs the item and submits the bytes.",
)


def _open_requirement(**overrides) -> EvidenceRequirement:
    values = dict(
        id="req-clock",
        predicate="device-A's clock offset is established",
        acceptable_source_class="operator photograph",
        responsibility=TaskResponsibility(owner="investigator-A", status=TaskStatus.ASSIGNED),
        discriminating_question="Does device-A's clock match the reference clock within one minute?",
        answer_classes=["clock_matches_reference", "clock_offset_detected", "not_determinable"],
    )
    values.update(overrides)
    return EvidenceRequirement(**values)


def _hypothesis(hyp_id="hyp-2", requirement_id="req-clock") -> Hypothesis:
    return Hypothesis(
        id=hyp_id,
        explanation="Device A's clock was correct at seizure.",
        discriminating_requirement_id=requirement_id,
    )


def _capture_mandate(**overrides) -> Mandate:
    values = dict(
        id="mandate-capture-001",
        issuer="legal-authority-001",
        principal="investigator-A",
        resources=["case-001/operator-intake"],
        operations=["capture", "derive_annotation"],
        destinations=["local-only"],
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=5),
    )
    values.update(overrides)
    return Mandate(**values)


def _route(requirement=None, hypotheses=None, mandate="default", sources=None):
    return acquisition_route(
        case_id="case-001",
        requirement=requirement or _open_requirement(),
        hypotheses=[_hypothesis()] if hypotheses is None else hypotheses,
        capture_mandate=_capture_mandate() if mandate == "default" else mandate,
        sources=[SOURCE] if sources is None else sources,
        now=NOW,
    )


def test_open_discriminating_requirement_with_granted_source_has_a_route():
    route = _route()
    assert isinstance(route, AcquisitionRoute)
    assert route.resource == "case-001/operator-intake"
    assert route.hypothesis_ids == ("hyp-2",)
    assert route.answer_classes[0] == "clock_matches_reference"


@pytest.mark.parametrize(
    "kwargs, reason_fragment",
    [
        ({"requirement": _open_requirement(resolved=True)}, "already resolved"),
        ({"requirement": _open_requirement(unresolvable=True, unresolvable_reason="device wiped")}, "unresolvable"),
        ({"requirement": _open_requirement(blocked_by_authority=True)}, "blocked"),
        ({"requirement": _open_requirement(discriminating_question=None, answer_classes=[])}, "no discriminating question"),
        ({"hypotheses": []}, "discriminate nothing"),
        ({"hypotheses": [_hypothesis(requirement_id="req-other")]}, "discriminate nothing"),
        ({"sources": []}, "no configured source"),
        ({"sources": [SOURCE, SOURCE.model_copy(update={"source_id": "second"})]}, "more than one"),
        ({"mandate": None}, "no capture mandate"),
        ({"mandate": _capture_mandate(revoked=True, revoked_reason="reassigned")}, "revoked"),
        ({"mandate": _capture_mandate(valid_until=NOW - timedelta(minutes=1))}, "closed"),
        ({"mandate": _capture_mandate(operations=["derive_annotation"])}, "operation 'capture'"),
        ({"mandate": _capture_mandate(resources=["case-001/device-A"])}, "resource"),
    ],
)
def test_every_missing_condition_refuses_with_its_reason(kwargs, reason_fragment):
    refusal = _route(**kwargs)
    assert isinstance(refusal, RouteRefusal)
    assert reason_fragment in refusal.reason


def test_answer_classes_without_a_question_or_with_one_class_are_rejected():
    with pytest.raises(ValueError):
        _open_requirement(discriminating_question=None)
    with pytest.raises(ValueError):
        _open_requirement(answer_classes=["only_one"])
    with pytest.raises(ValueError):
        _open_requirement(answer_classes=["same", "same"])


def test_need_snapshot_matches_what_the_gate_recomputes_in_its_transaction():
    requirement = _open_requirement()
    hypotheses = [_hypothesis("hyp-3"), _hypothesis("hyp-2"), _hypothesis("hyp-x", "req-other")]
    need = need_snapshot_for(case_id="case-001", requirement=requirement, hypotheses=hypotheses)
    assert need.hypothesis_ids == ("hyp-2", "hyp-3")
    linked = sorted((h for h in hypotheses if h.discriminating_requirement_id == requirement.id), key=lambda h: h.id)
    SQLiteAcquisitionGate._validate_current_need(need, requirement, linked)

    reworded = _open_requirement(discriminating_question="Is the clock roughly right?")
    with pytest.raises(ValueError, match="stale"):
        SQLiteAcquisitionGate._validate_current_need(need, reworded, linked)


def _unverified(req_id, observation_id):
    return EvidenceRequirement(
        id=req_id,
        predicate=f"{observation_id} was acquired following the documented procedure",
        acceptable_source_class="operator photograph",
        observation_id=observation_id,
        responsibility=TaskResponsibility(
            owner="investigator-A", status=TaskStatus.REPORTED_DONE, reported_done_by="investigator-A"
        ),
    )


def _prepare(two_device_case, requirements, resolvable):
    observations, files, _ = two_device_case
    decision, prepared = prepare_evidence_package(
        proposed_action=_proposed_action(),
        mandate=_mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
        resolvable_requirement_ids=resolvable,
    )
    return decision, prepared


def test_unverified_evidence_with_a_route_for_every_gap_is_gather_evidence(two_device_case):
    requirements = [_verified_requirement("req-a1", "obs-a1"), _unverified("req-a2", "obs-a2")]
    decision, prepared = _prepare(two_device_case, requirements, frozenset({"req-a2"}))
    assert decision.verdict == AuthorityVerdict.GATHER_EVIDENCE
    assert prepared is None


def test_without_a_route_the_same_gap_stays_forbidden(two_device_case):
    requirements = [_verified_requirement("req-a1", "obs-a1"), _unverified("req-a2", "obs-a2")]
    decision, _ = _prepare(two_device_case, requirements, frozenset())
    assert decision.verdict == AuthorityVerdict.FORBIDDEN


def test_a_route_for_only_some_gaps_is_not_enough(two_device_case):
    requirements = [_unverified("req-a1", "obs-a1"), _unverified("req-a2", "obs-a2")]
    decision, _ = _prepare(two_device_case, requirements, frozenset({"req-a2"}))
    assert decision.verdict == AuthorityVerdict.FORBIDDEN


def test_integrity_failure_is_never_resolvable_by_a_new_capture(two_device_case):
    observations, files, _ = two_device_case
    files["obs-a1"].write_bytes(b"tampered")
    requirements = [_verified_requirement("req-a1", "obs-a1"), _unverified("req-a2", "obs-a2")]
    decision, _ = _prepare(two_device_case, requirements, frozenset({"req-a1", "req-a2"}))
    assert decision.verdict == AuthorityVerdict.FORBIDDEN


def test_resolvable_ids_are_exactly_the_routable_requirements():
    ids = resolvable_requirement_ids(
        case_id="case-001",
        requirements=[_open_requirement(), _open_requirement(id="req-done", resolved=True)],
        hypotheses=[_hypothesis(), _hypothesis("hyp-9", "req-done")],
        capture_mandate=_capture_mandate(),
        sources=[SOURCE],
        now=NOW,
    )
    assert ids == frozenset({"req-clock"})
