"""Level 6 sub-mandates: a delegated authority can never exceed its parent,
and dies when its parent does. These are the falsifiable checks behind
krakadyl/core/delegation.py — each states the property it would take to break.
"""

from datetime import datetime, timedelta, timezone

import pytest

from krakadyl.core.delegation import (
    DelegationRejected,
    authority_under_chain,
    authority_under_delegation,
    derive_sub_mandate,
)
from krakadyl.core.models import AuthorityState, Mandate

NOW = datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc)


def parent(**overrides) -> Mandate:
    defaults = dict(
        id="mandate-001",
        issuer="legal-authority-001",
        principal="investigator-A",
        resources=["case-001/device-A", "case-001/device-B"],
        operations=["package_export", "inspect"],
        destinations=["reviewer-authorized", "lab-internal"],
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=5),
    )
    defaults.update(overrides)
    return Mandate(**defaults)


def _derive(p, **overrides):
    defaults = dict(
        id="submandate-001",
        principal="investigator-J",
        resources=["case-001/device-A"],
        operations=["package_export"],
        destinations=["reviewer-authorized"],
        valid_from=NOW,
        valid_until=NOW + timedelta(days=1),
        now=NOW,
    )
    defaults.update(overrides)
    return derive_sub_mandate(p, **defaults)


# --- static closure: a sub-mandate cannot be built wider than its parent ---

def test_narrower_sub_mandate_is_derivable_and_bound_to_its_parent():
    sub = _derive(parent())
    assert sub.parent_id == "mandate-001"
    assert sub.principal == "investigator-J"
    assert sub.issuer == "investigator-A"  # the delegator, by default


@pytest.mark.parametrize("field,bad", [
    ("resources", ["case-001/device-C"]),
    ("operations", ["delete"]),
    ("destinations", ["external-share"]),
])
def test_a_sub_mandate_cannot_widen_any_scope_dimension(field, bad):
    with pytest.raises(DelegationRejected, match="cannot widen"):
        _derive(parent(), **{field: bad})


def test_a_sub_mandate_cannot_start_before_its_parent():
    with pytest.raises(DelegationRejected, match="start before"):
        _derive(parent(), valid_from=NOW - timedelta(days=2))


def test_a_sub_mandate_cannot_outlive_a_bounded_parent():
    with pytest.raises(DelegationRejected, match="outlive"):
        _derive(parent(), valid_until=NOW + timedelta(days=10))


def test_a_sub_mandate_cannot_be_open_ended_under_a_bounded_parent():
    with pytest.raises(DelegationRejected, match="open-ended"):
        _derive(parent(), valid_until=None)


def test_cannot_delegate_from_a_revoked_parent():
    with pytest.raises(DelegationRejected, match="revoked"):
        _derive(parent(revoked=True, revoked_reason="scope withdrawn"))


def test_cannot_delegate_from_a_not_yet_effective_parent():
    future = parent(valid_from=NOW + timedelta(days=1))
    with pytest.raises(DelegationRejected, match="take effect"):
        _derive(future, valid_from=NOW + timedelta(days=1), valid_until=NOW + timedelta(days=2))


# --- dynamic composition: the effective authority is the more restrictive ---

def test_authority_granted_for_a_triple_within_both():
    p = parent()
    sub = _derive(p)
    check = authority_under_delegation(
        sub, p, resource="case-001/device-A", operation="package_export",
        destination="reviewer-authorized", now=NOW,
    )
    assert check.authority_state == AuthorityState.GRANTED


def test_the_sub_mandate_binds_even_when_the_parent_would_allow_more():
    # The parent holds device-B; the sub does not. The sub is the limit.
    p = parent()
    sub = _derive(p, resources=["case-001/device-A"])
    check = authority_under_delegation(
        sub, p, resource="case-001/device-B", operation="package_export",
        destination="reviewer-authorized", now=NOW,
    )
    assert check.authority_state == AuthorityState.DENIED
    assert check.outside_scope is True


def test_revoking_the_parent_after_derivation_revokes_the_delegated_authority():
    # The sub object is unchanged and still looks valid on its own, but the
    # parent has since been revoked — the delegated grant must die with it.
    p = parent()
    sub = _derive(p)
    revoked_parent = parent(revoked=True, revoked_reason="investigation reassigned", revision="2")
    check = authority_under_delegation(
        sub, revoked_parent, resource="case-001/device-A", operation="package_export",
        destination="reviewer-authorized", now=NOW,
    )
    assert check.authority_state == AuthorityState.DENIED
    assert any("parent mandate" in r and "revoked" in r for r in check.reasons)


def test_parent_expiry_after_derivation_expires_the_delegated_authority():
    p = parent()
    sub = _derive(p)
    later = NOW + timedelta(days=6)  # past the parent's valid_until, within nothing
    check = authority_under_delegation(
        sub, p, resource="case-001/device-A", operation="package_export",
        destination="reviewer-authorized", now=later,
    )
    assert check.authority_state == AuthorityState.EXPIRED
    assert any("parent mandate" in r for r in check.reasons)


def test_authority_refuses_a_mismatched_parent_binding():
    p = parent()
    sub = _derive(p)
    stranger = parent(id="mandate-999")
    with pytest.raises(DelegationRejected, match="names parent"):
        authority_under_delegation(
            sub, stranger, resource="case-001/device-A", operation="package_export",
            destination="reviewer-authorized", now=NOW,
        )


# --- full ancestor-chain walk (root -> mid -> leaf) ---

def _chain():
    root = parent(id="mandate-root")
    mid = derive_sub_mandate(
        root, id="mandate-mid", principal="investigator-lead",
        resources=["case-001/device-A", "case-001/device-B"],
        operations=["package_export", "inspect"],
        destinations=["reviewer-authorized", "lab-internal"],
        valid_from=NOW, valid_until=NOW + timedelta(days=3), now=NOW,
    )
    leaf = derive_sub_mandate(
        mid, id="mandate-leaf", principal="investigator-J",
        resources=["case-001/device-A"], operations=["package_export"],
        destinations=["reviewer-authorized"],
        valid_from=NOW, valid_until=NOW + timedelta(days=1), now=NOW,
    )
    return root, mid, leaf


def _granted(leaf, by_id, now=NOW, resource="case-001/device-A"):
    return authority_under_chain(
        leaf, by_id, resource=resource, operation="package_export",
        destination="reviewer-authorized", now=now,
    )


def test_chain_grants_a_triple_within_every_link():
    root, mid, leaf = _chain()
    check = _granted(leaf, {root.id: root, mid.id: mid})
    assert check.authority_state == AuthorityState.GRANTED


def test_leaf_binds_transitively_below_the_root():
    # device-B is held by the root and the mid, but the leaf dropped it.
    root, mid, leaf = _chain()
    check = _granted(leaf, {root.id: root, mid.id: mid}, resource="case-001/device-B")
    assert check.authority_state == AuthorityState.DENIED
    assert any("this sub-mandate" in r for r in check.reasons)


def test_revoking_the_distant_root_denies_the_leaf():
    root, mid, leaf = _chain()
    revoked_root = parent(id="mandate-root", revoked=True, revoked_reason="case closed", revision="2")
    check = _granted(leaf, {revoked_root.id: revoked_root, mid.id: mid})
    assert check.authority_state == AuthorityState.DENIED
    assert any("root mandate" in r and "revoked" in r for r in check.reasons)


def test_revoking_an_intermediate_ancestor_denies_the_leaf():
    root, mid, leaf = _chain()
    revoked_mid = Mandate(**{**mid.model_dump(), "revoked": True, "revoked_reason": "lead reassigned", "revision": "2"})
    check = _granted(leaf, {root.id: root, revoked_mid.id: revoked_mid})
    assert check.authority_state == AuthorityState.DENIED
    assert any("ancestor mandate 'mandate-mid'" in r for r in check.reasons)


def test_root_expiry_expires_the_whole_chain():
    root, mid, leaf = _chain()
    beyond = NOW + timedelta(days=6)  # past the root's valid_until
    check = _granted(leaf, {root.id: root, mid.id: mid}, now=beyond)
    assert check.authority_state == AuthorityState.EXPIRED
    assert any("root mandate" in r for r in check.reasons)


def test_a_broken_chain_is_rejected_not_silently_allowed():
    root, mid, leaf = _chain()
    with pytest.raises(DelegationRejected, match="broken"):
        _granted(leaf, {root.id: root})  # mid is missing


def test_a_cyclic_chain_is_rejected():
    a = Mandate(
        id="m-a", issuer="x", principal="p", resources=["r"], operations=["o"],
        destinations=["d"], valid_from=NOW - timedelta(days=1), valid_until=NOW + timedelta(days=1),
        parent_id="m-b",
    )
    b = Mandate(
        id="m-b", issuer="x", principal="p", resources=["r"], operations=["o"],
        destinations=["d"], valid_from=NOW - timedelta(days=1), valid_until=NOW + timedelta(days=1),
        parent_id="m-a",
    )
    with pytest.raises(DelegationRejected, match="cycle"):
        authority_under_chain(a, {a.id: a, b.id: b}, resource="r", operation="o", destination="d", now=NOW)
