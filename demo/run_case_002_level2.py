#!/usr/bin/env python3
"""Level 2, end to end: a prepared action goes stale, gets caught, and
recovers a still-legitimate route — or closes honestly when nothing can
fix it. Six real runs, no mocked decisions, no simulated file I/O:

1. Prepare an action while everything checks out.
2. Time passes, a file is tampered — execute catches the staleness,
   nothing is published.
3. propose_recovery_route excludes exactly the tampered resource.
4. The recovered action executes for real; the manifest records *why*
   the excluded resource is missing, not just that it's missing.
5. A mandate revoked in the gap — recovery correctly refuses to even
   attempt (no resource exclusion fixes a missing permission) and
   closes honestly instead.
6. The hypothesis half: a Hypothesis whose discriminating requirement
   turns out unresolvable gets flagged for review, even though it was
   already ACCEPTED.

Run: python demo/run_case_002_level2.py
Output lands in ./out/case-002/ (gitignored).
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo.run_case_001 import NOW, make_observation, mandate, verified_requirement
from krakadyl.core.executor import (
    execute_prepared_action,
    prepare_evidence_package,
    propose_recovery_route,
)
from krakadyl.core.invalidation import find_hypotheses_needing_review
from krakadyl.core.models import Hypothesis, HypothesisStatus, ProposedAction

OUT = Path(__file__).resolve().parent.parent / "out" / "case-002"


def action(action_id: str) -> ProposedAction:
    return ProposedAction(
        id=action_id,
        operation="package_export",
        arguments={"device": "device-A", "destination": "reviewer-authorized"},
        expected_effect="assemble a reviewer-ready package of device A's evidence only",
        mission_id="case-001",
    )


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    raw = OUT / "raw"
    raw.mkdir(parents=True)

    observations = [
        make_observation("obs-a1", "device-A", raw / "a1.jpg", b"device A photo one, authentic bytes"),
        make_observation("obs-a2", "device-A", raw / "a2.jpg", b"device A photo two, authentic bytes"),
    ]
    files = {"obs-a1": raw / "a1.jpg", "obs-a2": raw / "a2.jpg"}
    requirements = [verified_requirement("obs-a1"), verified_requirement("obs-a2")]

    # --- 1. Prepare while everything checks out. ---
    decision, prepared = prepare_evidence_package(
        proposed_action=action("action-101"),
        mandate=mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )
    print("=== 1. Prepared while everything checks out ===")
    print(f"verdict: {decision.verdict.value}")
    assert prepared is not None

    # --- Time passes: obs-a1 is tampered. ---
    files["obs-a1"].write_bytes(b"tampered content, does not match the acquired digest")

    receipt = execute_prepared_action(
        prepared=prepared,
        decision=decision,
        proposed_action=action("action-101"),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        current_mandate=mandate(),
        consumed_nonces=set(),
        out_dir=OUT / "package-attempt",
        now=NOW,
    )
    print("\n=== 2. Execute catches the staleness — nothing published ===")
    print(f"executed: {receipt.executed}")
    print(f"effect:   {receipt.observed_effect}")
    assert receipt.executed is False
    assert not (OUT / "package-attempt" / "manifest.json").exists()

    # --- 3. Recover a still-legitimate route. ---
    outcome = propose_recovery_route(
        proposed_action=action("action-102"),
        mandate=mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )
    print("\n=== 3. Recovery: exclude exactly the failing resource ===")
    print(f"attempted:          {outcome.attempted}")
    print(f"excluded_resources: {outcome.excluded_resources}")
    assert outcome.recovered_prepared is not None

    # The caller carries the same reduced observations/requirements
    # through to execute — there is no persistence layer yet that would
    # let execute rediscover "this was deliberately excluded" on its own.
    reduced_observations = [o for o in observations if o.id not in outcome.excluded_resources]
    reduced_requirements = [r for r in requirements if r.observation_id not in outcome.excluded_resources]

    recovered_receipt = execute_prepared_action(
        prepared=outcome.recovered_prepared,
        decision=outcome.recovered_decision,
        proposed_action=action("action-102"),
        observations=reduced_observations,
        requirements=reduced_requirements,
        observation_files=files,
        current_mandate=mandate(),
        consumed_nonces=set(),
        out_dir=OUT / "package-recovered",
        now=NOW,
    )
    print("\n=== 4. Recovered action executes for real ===")
    print(f"executed: {recovered_receipt.executed}")
    print(f"effect:   {recovered_receipt.observed_effect}")
    assert recovered_receipt.executed is True
    manifest = json.loads((OUT / "package-recovered" / "manifest.json").read_text())
    print(f"manifest excluded_resources: {manifest['excluded_resources']}")

    # --- 5. A mandate-level problem — recovery must not pretend to fix it. ---
    revoked_mandate = mandate(revision="2", revoked=True, revoked_reason="case reassigned to another unit")
    mandate_outcome = propose_recovery_route(
        proposed_action=action("action-103"),
        mandate=revoked_mandate,
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device="device-A",
        destination="reviewer-authorized",
        now=NOW,
    )
    print("\n=== 5. Mandate revoked — recovery refuses to attempt, closes honestly ===")
    print(f"attempted:     {mandate_outcome.attempted}")
    print(f"closed_reason: {mandate_outcome.closed_reason}")
    assert mandate_outcome.attempted is False

    # --- 6. The hypothesis half of Level 2. ---
    hyp = Hypothesis(
        id="hyp-001",
        explanation="Device A's photos were taken at the scene before device B arrived.",
        status=HypothesisStatus.ACCEPTED,
        discriminating_requirement_id="req-timestamp-check",
    )
    timestamp_requirement = verified_requirement("obs-a1")
    timestamp_requirement.id = "req-timestamp-check"
    # It later turns out this can't actually be resolved this way — the
    # device clock was never synced, so comparing timestamps is
    # meaningless. An already-ACCEPTED hypothesis is not exempt from
    # being flagged for this.
    timestamp_requirement.resolved = False
    timestamp_requirement.unresolvable = True
    timestamp_requirement.unresolvable_reason = "device clock was never synced; timestamp comparison is meaningless"

    flagged = find_hypotheses_needing_review([hyp], [timestamp_requirement])
    print("\n=== 6. An ACCEPTED hypothesis whose discriminating requirement became unresolvable ===")
    for hyp_id, reason in flagged:
        print(f"{hyp_id}: {reason}")
    assert flagged and flagged[0][0] == "hyp-001"

    print(f"\nAll output under: {OUT}")


if __name__ == "__main__":
    main()
