"""Level 2, second half: a Hypothesis is flagged for review when the
EvidenceRequirement that discriminates it is no longer resolved.
"""

from datetime import datetime, timezone

from krakadyl.core.invalidation import find_hypotheses_needing_review
from krakadyl.core.models import EvidenceRequirement, Hypothesis, TaskResponsibility, TaskStatus

NOW = datetime(2026, 10, 27, 19, 0, tzinfo=timezone.utc)


def _requirement(req_id: str, *, resolved: bool, unresolvable: bool = False, reason=None) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=req_id,
        predicate="which device captured this photo",
        acceptable_source_class="device manifest",
        resolved=resolved,
        unresolvable=unresolvable,
        unresolvable_reason=reason,
        responsibility=TaskResponsibility(owner="investigator-A", status=TaskStatus.UNASSIGNED),
    )


def _hypothesis(h_id: str, discriminating_requirement_id, status="proposed") -> Hypothesis:
    return Hypothesis(
        id=h_id,
        explanation="photo belongs to device A",
        status=status,
        discriminating_requirement_id=discriminating_requirement_id,
    )


def test_resolved_requirement_means_no_flag():
    req = _requirement("req-1", resolved=True)
    h = _hypothesis("hyp-1", "req-1")
    assert find_hypotheses_needing_review([h], [req]) == []


def test_requirement_reverting_to_unresolved_flags_the_hypothesis():
    req = _requirement("req-1", resolved=False)
    h = _hypothesis("hyp-1", "req-1")
    flagged = find_hypotheses_needing_review([h], [req])
    assert flagged == [("hyp-1", "discriminating requirement 'req-1' is no longer resolved")]


def test_accepted_hypothesis_is_not_exempt_this_is_the_important_case():
    """Correction built into the design: an accepted hypothesis whose
    grounds later became unresolvable is exactly the case to catch —
    'accepted' must NOT mean 'stop checking.'
    """
    req = _requirement("req-1", resolved=False, unresolvable=True, reason="the only witness retracted")
    h = _hypothesis("hyp-1", "req-1", status="accepted")
    flagged = find_hypotheses_needing_review([h], [req])
    assert len(flagged) == 1
    assert "the only witness retracted" in flagged[0][1]


def test_rejected_hypothesis_is_skipped_not_noise():
    req = _requirement("req-1", resolved=False, unresolvable=True, reason="irrelevant now")
    h = _hypothesis("hyp-1", "req-1", status="rejected")
    assert find_hypotheses_needing_review([h], [req]) == []


def test_hypothesis_with_no_discriminating_requirement_is_never_flagged():
    h = _hypothesis("hyp-1", None)
    assert find_hypotheses_needing_review([h], []) == []


def test_dangling_reference_to_a_deleted_requirement_is_caught_not_crashed_on():
    h = _hypothesis("hyp-1", "req-does-not-exist")
    flagged = find_hypotheses_needing_review([h], [])
    assert flagged == [("hyp-1", "discriminating requirement 'req-does-not-exist' no longer exists in this case")]
