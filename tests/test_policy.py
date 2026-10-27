from krakadyl.core.models import AuthorityState, AuthorityVerdict, EvidenceState
from krakadyl.core.policy import decide


def test_gather_evidence_when_missing_but_source_available():
    verdict, reasons = decide(
        evidence_state=EvidenceState.MISSING,
        authority_state=AuthorityState.GRANTED,
        outside_mandate_scope=False,
        resolvable_by_authorized_source=True,
    )
    assert verdict == AuthorityVerdict.GATHER_EVIDENCE
    assert reasons


def test_confirm_when_decision_belongs_to_person():
    verdict, _ = decide(
        evidence_state=EvidenceState.SUFFICIENT,
        authority_state=AuthorityState.NEEDS_CONSENT,
        outside_mandate_scope=False,
        resolvable_by_authorized_source=False,
    )
    assert verdict == AuthorityVerdict.CONFIRM


def test_forbidden_when_outside_mandate_scope_even_with_full_evidence():
    verdict, _ = decide(
        evidence_state=EvidenceState.SUFFICIENT,
        authority_state=AuthorityState.GRANTED,
        outside_mandate_scope=True,
        resolvable_by_authorized_source=False,
    )
    assert verdict == AuthorityVerdict.FORBIDDEN


def test_forbidden_when_no_authorized_source_remains():
    verdict, _ = decide(
        evidence_state=EvidenceState.CONFLICTING,
        authority_state=AuthorityState.GRANTED,
        outside_mandate_scope=False,
        resolvable_by_authorized_source=False,
    )
    assert verdict == AuthorityVerdict.FORBIDDEN


def test_allowed_when_sufficient_and_granted():
    verdict, _ = decide(
        evidence_state=EvidenceState.SUFFICIENT,
        authority_state=AuthorityState.GRANTED,
        outside_mandate_scope=False,
        resolvable_by_authorized_source=False,
    )
    assert verdict == AuthorityVerdict.ALLOWED


def test_expired_mandate_is_forbidden_not_confirm():
    verdict, _ = decide(
        evidence_state=EvidenceState.SUFFICIENT,
        authority_state=AuthorityState.EXPIRED,
        outside_mandate_scope=False,
        resolvable_by_authorized_source=False,
    )
    assert verdict == AuthorityVerdict.FORBIDDEN


def test_a_classification_signal_alone_never_grants_authority():
    """Regression guard for the Oct 26 correction: Laya (or the model)
    classifying something as low-risk must not, by itself, change the
    verdict unless it also changed the verifiable authority_state/
    evidence_state fed into decide(). This test documents the invariant
    at the API level: decide() has no parameter through which a
    probabilistic signal could enter as if it were a verified fact.
    """
    import inspect

    params = set(inspect.signature(decide).parameters)
    assert params == {
        "evidence_state",
        "authority_state",
        "outside_mandate_scope",
        "resolvable_by_authorized_source",
    }
