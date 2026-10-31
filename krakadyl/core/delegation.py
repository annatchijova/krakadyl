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
