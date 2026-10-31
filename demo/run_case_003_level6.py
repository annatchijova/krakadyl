#!/usr/bin/env python3
"""Level 6 demo — sub-mandates: delegating a strictly narrower slice of
authority, and watching it die when its parent does.

No network, no model: pure deterministic authority. A senior investigator
holds a broad mandate over a case; they delegate a narrower sub-mandate to a
junior for one device, one operation, one destination, for one day. The junior
can act within it; they cannot be given — and cannot acquire — anything the
senior did not hold; and the moment the senior's mandate is revoked, the
junior's delegated authority is revoked with it, without touching the junior's
mandate object at all.

Run: python demo/run_case_003_level6.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from krakadyl.core.delegation import (
    DelegationRejected,
    authority_under_delegation,
    derive_sub_mandate,
)
from krakadyl.core.models import Mandate

NOW = datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc)


def report_authority(title, check):
    print(f"\n=== {title} ===")
    print(f"authority: {check.authority_state.value}")
    print(f"reasons:   {check.reasons}")


def main() -> None:
    senior = Mandate(
        id="mandate-senior-001",
        issuer="legal-authority-001",
        principal="investigator-A",
        resources=["case-001/device-A", "case-001/device-B"],
        operations=["package_export", "inspect"],
        destinations=["reviewer-authorized", "lab-internal"],
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=5),
    )
    print("Senior mandate (investigator-A): device-A+device-B, package_export+inspect,")
    print("reviewer-authorized+lab-internal, valid 6 days.")

    # 1. Delegate a strictly narrower slice to a junior.
    sub = derive_sub_mandate(
        senior,
        id="mandate-junior-001",
        principal="investigator-J",
        resources=["case-001/device-A"],
        operations=["package_export"],
        destinations=["reviewer-authorized"],
        valid_from=NOW,
        valid_until=NOW + timedelta(days=1),
        now=NOW,
    )
    print(f"\nDelegated sub-mandate to investigator-J (parent={sub.parent_id}):")
    print("  device-A only, package_export only, reviewer-authorized only, 1 day.")

    # 2. The junior acts within the delegated slice — granted.
    report_authority(
        "1. Junior exports device-A to the authorized reviewer (within the slice)",
        authority_under_delegation(
            sub, senior, resource="case-001/device-A", operation="package_export",
            destination="reviewer-authorized", now=NOW,
        ),
    )

    # 3. The junior reaches for device-B — the senior holds it, the slice does not.
    report_authority(
        "2. Junior reaches for device-B (the senior holds it; the slice does not)",
        authority_under_delegation(
            sub, senior, resource="case-001/device-B", operation="package_export",
            destination="reviewer-authorized", now=NOW,
        ),
    )

    # 4. You cannot even build a sub-mandate that widens the parent.
    print("\n=== 3. Trying to delegate authority the senior never held ===")
    try:
        derive_sub_mandate(
            senior,
            id="mandate-junior-bad",
            principal="investigator-J",
            resources=["case-001/device-A"],
            operations=["package_export"],
            destinations=["external-share"],  # senior never had this
            valid_from=NOW,
            valid_until=NOW + timedelta(days=1),
            now=NOW,
        )
        print("BUG: a widening sub-mandate was constructed")
    except DelegationRejected as exc:
        print(f"refused at construction: {exc}")

    # 5. Revoke the senior mandate. The junior's object is unchanged, but the
    #    delegated authority is gone — composition closure at authority time.
    revoked_senior = Mandate(
        **{**senior.model_dump(), "revoked": True,
           "revoked_reason": "investigation reassigned", "revision": "2"}
    )
    report_authority(
        "4. Senior mandate revoked — the same junior action, re-checked",
        authority_under_delegation(
            sub, revoked_senior, resource="case-001/device-A", operation="package_export",
            destination="reviewer-authorized", now=NOW,
        ),
    )
    print("\nThe junior's sub-mandate was never touched; revoking the parent was enough.")


if __name__ == "__main__":
    main()
