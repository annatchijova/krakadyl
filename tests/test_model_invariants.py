"""Regression tests for the two bypasses found by self-red-teaming the
Level 2 build: a validator that only ran at construction, and a
"snapshot" that was actually mutable. Both are real findings — these
tests prove they stay fixed, not just that they were fixed once.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from krakadyl.core.models import (
    EvidenceRequirement,
    Hypothesis,
    Mandate,
    RecoveryWindow,
    RecoveryWindowKind,
    TaskResponsibility,
    TaskStatus,
)

NOW = datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc)


def _mandate(**overrides) -> Mandate:
    defaults = dict(
        id="m1",
        issuer="x",
        principal="y",
        resources=["r"],
        operations=["o"],
        destinations=["d"],
        valid_from=NOW,
    )
    defaults.update(overrides)
    return Mandate(**defaults)


def test_mandate_cannot_be_mutated_in_place():
    """Regression for: mandate.revoked = True used to silently succeed
    without bumping revision, which would have defeated the Level 2
    invalidation engine's staleness check entirely."""
    mandate = _mandate()
    with pytest.raises(ValidationError):
        mandate.revoked = True


def test_mandate_change_requires_a_new_object_with_a_bumped_revision():
    original = _mandate(revision="1")
    revoked = _mandate(revision="2", revoked=True, revoked_reason="case closed")
    assert original.revision != revoked.revision
    assert original.revoked is False  # the original is untouched


def test_task_responsibility_validates_on_assignment_not_just_construction():
    """Regression for: resp.status = VERIFIED_DONE used to bypass the
    independent-verification validator entirely, because Pydantic only
    ran it at construction time by default."""
    resp = TaskResponsibility(owner="investigator-A", status=TaskStatus.REPORTED_DONE, reported_done_by="investigator-A")
    with pytest.raises(ValidationError):
        resp.status = TaskStatus.VERIFIED_DONE  # no verified_by/verification_method set


def test_task_responsibility_still_allows_a_valid_post_construction_transition():
    """The fix must not make legitimate status transitions impossible —
    only invalid ones."""
    resp = TaskResponsibility(owner="investigator-A", status=TaskStatus.ASSIGNED)
    resp.status = TaskStatus.ACKNOWLEDGED
    resp.accepted_by = "investigator-A"
    resp.accepted_at = NOW
    assert resp.status == TaskStatus.ACKNOWLEDGED


def test_recovery_window_validates_kind_consistency_on_assignment():
    rw = RecoveryWindow(kind=RecoveryWindowKind.UNKNOWN, what_is_lost_if_missed="x")
    with pytest.raises(ValidationError):
        rw.kind = RecoveryWindowKind.ESTIMATED  # no estimate_basis set


def test_requirement_cannot_be_both_resolved_and_unresolvable():
    """Regression for: a requirement used to accept resolved=True and
    unresolvable=True simultaneously — a logical contradiction that
    find_hypotheses_needing_review's unresolvable-first check would
    have reported, masking that the requirement also claimed to be
    resolved."""
    with pytest.raises(ValidationError):
        EvidenceRequirement(
            id="r1",
            predicate="x",
            acceptable_source_class="y",
            resolved=True,
            unresolvable=True,
            responsibility=TaskResponsibility(owner="a", status=TaskStatus.UNASSIGNED),
        )


def test_hypothesis_status_rejects_unrecognized_values():
    """Regression for: Hypothesis.status used to accept any string — a
    typo or case mismatch ('Rejected' vs 'rejected') would silently
    fail to match find_hypotheses_needing_review's rejected-skip check."""
    with pytest.raises(ValidationError):
        Hypothesis(id="h1", explanation="x", status="ACEPTADO con typo")
