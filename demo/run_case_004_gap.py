#!/usr/bin/env python3
"""Level 6 demo — mission continuity across a real-time gap.

No network, no model. An investigator leaves a case on day 0 and picks it up
four days later. resume_after_gap reports exactly what changed in between because
time passed: a delegated sub-mandate lapsed, one recovery window closed, another
is still open (and now the most urgent), and a conditional one stays on watch.

Run: python demo/run_case_004_gap.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from krakadyl.core.continuity import resume_after_gap
from krakadyl.core.models import (
    EvidenceRequirement,
    Mandate,
    RecoveryWindow,
    RecoveryWindowKind,
    TaskResponsibility,
    TaskStatus,
)

LEFT = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)      # last activity
BACK = LEFT + timedelta(days=4, hours=3)                       # returns


def requirement(req_id, *, kind, until=None, condition=None):
    return EvidenceRequirement(
        id=req_id, predicate=f"{req_id} acquired", acceptable_source_class="tool",
        observation_id=f"obs-{req_id}",
        responsibility=TaskResponsibility(owner="investigator-J", status=TaskStatus.ASSIGNED),
        recovery_window=RecoveryWindow(
            kind=kind, until=until, condition=condition,
            what_is_lost_if_missed=f"the {req_id} source",
        ),
    )


def main() -> None:
    mandates = [
        Mandate(id="mandate-001", issuer="court", principal="investigator-A",
                resources=["r"], operations=["o"], destinations=["d"],
                valid_from=LEFT - timedelta(days=1), valid_until=BACK + timedelta(days=10)),
        # A delegation the senior granted the junior for two days — lapsed while away.
        Mandate(id="mandate-junior", issuer="investigator-A", principal="investigator-J",
                resources=["r"], operations=["o"], destinations=["d"],
                valid_from=LEFT, valid_until=LEFT + timedelta(days=2), parent_id="mandate-001"),
    ]
    requirements = [
        requirement("req-cctv", kind=RecoveryWindowKind.KNOWN, until=LEFT + timedelta(days=1)),   # closed while away
        requirement("req-logs", kind=RecoveryWindowKind.KNOWN, until=BACK + timedelta(hours=6)),  # still open, soon
        requirement("req-archive", kind=RecoveryWindowKind.KNOWN, until=BACK + timedelta(days=3)),# still open, later
        requirement("req-device", kind=RecoveryWindowKind.CONDITIONAL, condition="the phone is powered off"),
    ]

    briefing = resume_after_gap(requirements=requirements, mandates=mandates, since=LEFT, now=BACK)

    print(briefing.headline)
    print(f"\ngap: {briefing.gap_human} ({briefing.gap_seconds} seconds)")
    print(f"mandates expired while away:   {list(briefing.mandates_expired_while_away)}")
    print(f"  of which delegations lapsed: {list(briefing.delegations_expired_while_away)}")
    print("recovery windows closed while away:")
    for item in briefing.recovery_closed_while_away:
        print(f"  - {item.requirement_id}: lost {item.what_is_lost_if_missed} (closed {item.at.isoformat()})")
    print("recovery windows still open (soonest first):")
    for item in briefing.recovery_still_open:
        print(f"  - {item.requirement_id}: until {item.at.isoformat()}")
    print(f"on conditional/unknown watch:  {list(briefing.conditional_or_unknown_watch)}")


if __name__ == "__main__":
    main()
