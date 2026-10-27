"""Level 2 Cycle 4: propose a new discriminating question without
claiming that the answer, evidence, or verification already exists.
"""

from datetime import datetime, timezone

import pytest

from krakadyl.core.invalidation import propose_hypothesis_recovery
from krakadyl.core.models import (
    EvidenceRequirement,
    Hypothesis,
    RecoveryWindow,
    RecoveryWindowKind,
    TaskResponsibility,
    TaskStatus,
)

NOW = datetime(2026, 10, 27, 20, 0, tzinfo=timezone.utc)


def _requirement(
    req_id: str,
    *,
    predicate: str = "which device captured this photo",
    source_class: str = "device manifest",
    resolved: bool = False,
    unresolvable: bool = False,
    observation_id: str | None = None,
    blocked_by_authority: bool = False,
    blocked_reason: str | None = None,
    owner: str = "investigator-A",
    recovery_window: RecoveryWindow | None = None,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        predicate=predicate,
        acceptable_source_class=source_class,
        freshness_requirement="captured during the current case",
        observation_id=observation_id,
        resolved=resolved,
        unresolvable=unresolvable,
        unresolvable_reason="the original source was destroyed" if unresolvable else None,
        recovery_window=recovery_window,
        blocked_by_authority=blocked_by_authority,
        blocked_reason=blocked_reason,
        responsibility=TaskResponsibility(
            owner=owner,
            status=TaskStatus.VERIFIED_DONE if resolved else TaskStatus.REPORTED_DONE,
            reported_done_by=owner,
            verified_by="investigator-C" if resolved else None,
            verification_method="peer-review" if resolved else None,
        ),
    )


def _hypothesis(*, status: str = "accepted", requirement_id: str | None = "req-failed") -> Hypothesis:
    return Hypothesis(
        id="hyp-1",
        explanation="the photo belongs to device A",
        status=status,
        discriminating_requirement_id=requirement_id,
    )


def _alternative_source() -> EvidenceRequirement:
    return _requirement(
        "req-source-catalog",
        predicate="the backup manifest is present in the case source catalog",
        source_class="case-held backup device manifest",
        resolved=True,
    )


def test_proposes_a_new_open_question_from_an_explicit_case_source():
    old = _requirement(
        "req-failed",
        unresolvable=True,
        recovery_window=RecoveryWindow(
            kind=RecoveryWindowKind.CONDITIONAL,
            condition="the damaged device is discarded",
            what_is_lost_if_missed="the original manifest",
        ),
    )
    source = _alternative_source()
    hypothesis = _hypothesis()
    old_before = old.model_dump()
    source_before = source.model_dump()
    hypothesis_before = hypothesis.model_dump()

    outcome = propose_hypothesis_recovery(
        hypothesis,
        [old, source],
        alternative_source_requirement_id=source.id,
    )

    assert outcome.attempted is True
    assert outcome.closed_reason is None
    suggested = outcome.suggested_new_requirement
    assert suggested is not None
    assert suggested.id not in {old.id, source.id}
    assert suggested.predicate == old.predicate
    assert suggested.acceptable_source_class == source.acceptable_source_class
    assert suggested.freshness_requirement == old.freshness_requirement
    assert suggested.resolved is False
    assert suggested.unresolvable is False
    assert suggested.unresolvable_reason is None
    assert suggested.observation_id is None
    assert suggested.recovery_window is None
    assert suggested.blocked_by_authority is False
    assert suggested.blocked_reason is None
    assert suggested.responsibility == TaskResponsibility(
        owner=old.responsibility.owner,
        status=TaskStatus.UNASSIGNED,
    )
    assert old.model_dump() == old_before
    assert source.model_dump() == source_before
    assert hypothesis.model_dump() == hypothesis_before


def test_recovery_id_is_deterministic_order_independent_and_idempotent():
    old = _requirement("req-failed", unresolvable=True)
    source = _alternative_source()
    first = propose_hypothesis_recovery(
        _hypothesis(),
        [old, source],
        alternative_source_requirement_id=source.id,
    )
    reordered = propose_hypothesis_recovery(
        _hypothesis(),
        [source, old],
        alternative_source_requirement_id=source.id,
    )
    assert first.suggested_new_requirement is not None
    assert reordered.suggested_new_requirement is not None
    assert first.suggested_new_requirement.id == reordered.suggested_new_requirement.id

    repeated = propose_hypothesis_recovery(
        _hypothesis(),
        [old, source, first.suggested_new_requirement],
        alternative_source_requirement_id=source.id,
    )
    assert repeated.attempted is False
    assert repeated.suggested_new_requirement is None
    assert "already exists" in repeated.closed_reason


@pytest.mark.parametrize(
    ("hypothesis", "requirements", "source_id", "reason_fragment"),
    [
        (_hypothesis(requirement_id="missing"), [_alternative_source()], "req-source-catalog", "no longer exists"),
        (_hypothesis(status="rejected"), [_requirement("req-failed", unresolvable=True)], None, "not flagged"),
        (_hypothesis(requirement_id=None), [], None, "not flagged"),
        (_hypothesis(), [_requirement("req-failed", resolved=True)], None, "not flagged"),
        (_hypothesis(), [_requirement("req-failed")], None, "still open"),
    ],
)
def test_does_not_duplicate_a_question_that_has_no_honest_recovery_trigger(
    hypothesis,
    requirements,
    source_id,
    reason_fragment,
):
    outcome = propose_hypothesis_recovery(
        hypothesis,
        requirements,
        alternative_source_requirement_id=source_id,
    )

    assert outcome.attempted is False
    assert outcome.suggested_new_requirement is None
    assert reason_fragment in outcome.closed_reason


@pytest.mark.parametrize(
    "failed",
    [
        _requirement("req-failed", predicate="   ", unresolvable=True),
        _requirement("req-failed", source_class="", unresolvable=True),
        _requirement("req-failed", observation_id="obs-1", unresolvable=True),
        _requirement("req-failed", blocked_by_authority=True, unresolvable=True),
        _requirement("req-failed", blocked_reason="new consent required", unresolvable=True),
    ],
)
def test_closes_when_the_failed_requirement_cannot_be_reframed_honestly(failed):
    outcome = propose_hypothesis_recovery(
        _hypothesis(),
        [failed, _alternative_source()],
        alternative_source_requirement_id="req-source-catalog",
    )

    assert outcome.attempted is False
    assert outcome.suggested_new_requirement is None
    assert outcome.closed_reason is not None


@pytest.mark.parametrize(
    "source",
    [
        None,
        _requirement("req-source-catalog"),
        _requirement("req-source-catalog", source_class=" "),
        _requirement("req-source-catalog", unresolvable=True),
        _requirement("req-source-catalog", blocked_by_authority=True),
        _requirement("req-source-catalog", blocked_reason="not authorized"),
    ],
)
def test_requires_an_explicit_usable_source_already_declared_in_the_case(source):
    requirements = [_requirement("req-failed", unresolvable=True)]
    if source is not None:
        requirements.append(source)

    outcome = propose_hypothesis_recovery(
        _hypothesis(),
        requirements,
        alternative_source_requirement_id=None if source is None else source.id,
    )

    assert outcome.attempted is False
    assert outcome.suggested_new_requirement is None
    assert outcome.closed_reason is not None


@pytest.mark.parametrize("source_id", ["req-missing", "req-failed"])
def test_rejects_a_missing_or_self_referential_alternative_source(source_id):
    outcome = propose_hypothesis_recovery(
        _hypothesis(),
        [_requirement("req-failed", unresolvable=True)],
        alternative_source_requirement_id=source_id,
    )

    assert outcome.attempted is False
    assert outcome.suggested_new_requirement is None
    assert outcome.closed_reason is not None


def test_duplicate_requirement_ids_close_as_ambiguous_instead_of_using_last_write_wins():
    outcome = propose_hypothesis_recovery(
        _hypothesis(),
        [
            _requirement("req-failed", unresolvable=True),
            _requirement("req-failed", unresolvable=True),
            _alternative_source(),
        ],
        alternative_source_requirement_id="req-source-catalog",
    )

    assert outcome.attempted is False
    assert outcome.suggested_new_requirement is None
    assert "duplicate requirement id" in outcome.closed_reason
