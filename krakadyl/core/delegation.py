"""Level 6 — sub-mandates: delegating a strictly narrower slice of authority.

A long investigation hands pieces of work to sub-investigators and sub-tasks
over days. Each delegation is itself a `Mandate`, derived from a parent, and the
one rule that makes delegation safe is composition closure: **a sub-mandate can
never grant more than its parent, and it dies the moment its parent does.**

Two places enforce that, deliberately separated:

- `derive_sub_mandate` enforces the *static* subset at construction: the child's
  resources, operations and destinations are subsets of the parent's, its
  validity window sits inside the parent's, and the parent must be valid right
  now to delegate from. A child that would widen, outlive, or start before its
  parent is refused — it cannot be built, so no later check has to catch it.

- `authority_under_delegation` enforces the *dynamic* bound at authority time:
  the effective authority for a (resource, operation, destination) triple is the
  more restrictive of the child and the parent evaluated against the current
  clock. So a parent revoked or expired *after* the child was derived revokes
  the child too, even though the frozen child object still looks valid on its
  own. `Mandate.parent_id` alone grants nothing; this function is the only place
  a delegated grant is decided, and it reuses the one `check_mandate`.

No float, no model output, no mutation: a delegation is a typed authority
construct built from immutable `Mandate` snapshots, exactly like a root mandate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from krakadyl.core.executor import MandateCheck, check_mandate
from krakadyl.core.models import AuthorityState, Mandate


class DelegationRejected(ValueError):
    """A proposed sub-mandate that would widen, outlive, start before, or
    detach from its parent, or be derived from a parent that is not currently
    valid."""


def _parent_currently_valid(parent: Mandate, now: datetime) -> Optional[str]:
    """None if the parent can delegate right now; otherwise the reason it
    cannot. A root mandate that is revoked, not yet in effect, or past its
    window cannot hand out authority it does not currently hold."""
    if parent.revoked:
        return f"parent mandate is revoked: {parent.revoked_reason}"
    if now < parent.valid_from:
        return f"parent mandate does not take effect until {parent.valid_from.isoformat()}"
    if parent.valid_until is not None and now > parent.valid_until:
        return "parent mandate's validity window has closed"
    return None


def derive_sub_mandate(
    parent: Mandate,
    *,
    id: str,
    principal: str,
    resources: list[str],
    operations: list[str],
    destinations: list[str],
    valid_from: datetime,
    now: datetime,
    valid_until: Optional[datetime] = None,
    issuer: Optional[str] = None,
    revision: str = "1",
) -> Mandate:
    """Build a sub-mandate strictly bounded by `parent`, or raise
    `DelegationRejected`. `issuer` defaults to the parent's principal — the
    person delegating a slice of the authority they hold. `now` is the moment
    of delegation, used only to confirm the parent is currently valid."""
    blocked = _parent_currently_valid(parent, now)
    if blocked:
        raise DelegationRejected(f"cannot delegate: {blocked}")

    widenings = []
    for label, child_values, parent_values in (
        ("resources", resources, parent.resources),
        ("operations", operations, parent.operations),
        ("destinations", destinations, parent.destinations),
    ):
        extra = sorted(set(child_values) - set(parent_values))
        if extra:
            widenings.append(f"{label} not held by the parent: {', '.join(extra)}")
    if widenings:
        raise DelegationRejected("a sub-mandate cannot widen its parent — " + "; ".join(widenings))

    if valid_from < parent.valid_from:
        raise DelegationRejected("a sub-mandate cannot start before its parent")
    if parent.valid_until is not None:
        if valid_until is None:
            raise DelegationRejected("a sub-mandate cannot be open-ended when its parent expires")
        if valid_until > parent.valid_until:
            raise DelegationRejected("a sub-mandate cannot outlive its parent")
    if valid_until is not None and valid_until <= valid_from:
        raise DelegationRejected("a sub-mandate's validity window must be non-empty")

    return Mandate(
        id=id,
        issuer=issuer if issuer is not None else parent.principal,
        principal=principal,
        resources=list(resources),
        operations=list(operations),
        destinations=list(destinations),
        valid_from=valid_from,
        valid_until=valid_until,
        revision=revision,
        parent_id=parent.id,
    )


def authority_under_delegation(
    sub_mandate: Mandate,
    parent: Mandate,
    *,
    resource: str,
    operation: str,
    destination: str,
    now: datetime,
) -> MandateCheck:
    """Decide a (resource, operation, destination) triple under a sub-mandate,
    bounded by its parent evaluated against the current clock. The result is the
    more restrictive of the two checks: a parent revoked or expired after
    derivation denies the delegated action even if the child still looks valid.

    Raises `DelegationRejected` if the objects are not actually parent/child —
    a binding mismatch is a programming or tampering error, not a denial."""
    if sub_mandate.parent_id != parent.id:
        raise DelegationRejected(
            f"sub-mandate names parent '{sub_mandate.parent_id}', not '{parent.id}'"
        )

    parent_check = check_mandate(
        parent, resource=resource, operation=operation, destination=destination, now=now
    )
    if parent_check.authority_state != AuthorityState.GRANTED:
        return MandateCheck(
            outside_scope=parent_check.outside_scope,
            authority_state=parent_check.authority_state,
            reasons=[f"parent mandate: {r}" for r in parent_check.reasons],
        )

    return check_mandate(
        sub_mandate, resource=resource, operation=operation, destination=destination, now=now
    )


def resolve_delegation_chain(
    mandate: Mandate, ancestors_by_id: dict[str, Mandate]
) -> list[Mandate]:
    """The leaf-to-root chain starting at `mandate`, following `parent_id`
    through `ancestors_by_id`. Raises `DelegationRejected` if an ancestor named
    in the chain is missing (a broken chain cannot be proven bounded) or if the
    chain loops (a cycle would otherwise walk forever and has no root to anchor
    authority on)."""
    chain = [mandate]
    seen = {mandate.id}
    current = mandate
    while current.parent_id is not None:
        parent = ancestors_by_id.get(current.parent_id)
        if parent is None:
            raise DelegationRejected(
                f"delegation chain is broken: ancestor '{current.parent_id}' of "
                f"'{current.id}' was not provided"
            )
        if parent.id in seen:
            raise DelegationRejected(f"delegation chain has a cycle at '{parent.id}'")
        chain.append(parent)
        seen.add(parent.id)
        current = parent
    return chain


def authority_under_chain(
    mandate: Mandate,
    ancestors_by_id: dict[str, Mandate],
    *,
    resource: str,
    operation: str,
    destination: str,
    now: datetime,
) -> MandateCheck:
    """Decide a (resource, operation, destination) triple under a full
    delegation chain: every mandate from the leaf up to the root must currently
    grant it, and the result is the most restrictive. Revoking or expiring ANY
    ancestor denies the leaf, even a distant root above an intermediate mandate
    that is still fine — the whole chain is the bound, not just the parent edge.

    `ancestors_by_id` must contain every ancestor named by a `parent_id` in the
    chain; a missing ancestor or a cycle is a `DelegationRejected`, never a
    silent allow. A root mandate (no parent) is checked directly."""
    chain = resolve_delegation_chain(mandate, ancestors_by_id)
    # Walk root -> leaf so the outermost authority that fails is reported first:
    # "the root is revoked" is a more useful cause than "the leaf is out of
    # scope" when both could apply.
    for link in reversed(chain):
        check = check_mandate(
            link, resource=resource, operation=operation, destination=destination, now=now
        )
        if check.authority_state != AuthorityState.GRANTED:
            if link.id == mandate.id:
                label = "this sub-mandate"
            elif link.parent_id is None:
                label = f"root mandate '{link.id}'"
            else:
                label = f"ancestor mandate '{link.id}'"
            return MandateCheck(
                outside_scope=check.outside_scope,
                authority_state=check.authority_state,
                reasons=[f"{label}: {r}" for r in check.reasons],
            )
    return MandateCheck(
        outside_scope=False,
        authority_state=AuthorityState.GRANTED,
        reasons=[f"granted across a delegation chain of {len(chain)} mandate(s)"],
    )
