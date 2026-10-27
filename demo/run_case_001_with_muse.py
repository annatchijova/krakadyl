#!/usr/bin/env python3
"""Same case as `run_case_001.py`, but the `ProposedAction` is generated
by a real call to Muse Spark instead of being hand-built — the piece
`docs/levels.md` marks as the one thing left before Level 1 is fully
complete.

This makes a REAL, BILLED call to the Meta Model API (Standard mode,
`muse-spark-1.3` — a few cents at most for a single short call; see the
project's own API-budget note for the full pricing table). It requires
`META_API_KEY` in the environment (loaded from `.env`, gitignored) and
does nothing silently: it prints what it's about to do before the call
and exits if the key is missing, same as the adapter does on its own.

Muse's output is a candidate, not an authorization — it is validated
against `ProposedActionCandidate`'s schema, then run through the exact
same `check_mandate`/`check_evidence`/`decide()` pipeline as the
hand-built action in `run_case_001.py`. If Muse proposes something
outside the mandate or against unverified evidence, the deterministic
engine refuses it exactly like it refuses a hand-built one — that
refusal, not Muse's proposal, is the actual acceptance criterion for
this script.

Run: python demo/run_case_001_with_muse.py
"""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo.run_case_001 import NOW, make_observation, mandate, report, verified_requirement
from krakadyl.adapters.muse import MuseAdapterError, propose_action
from krakadyl.core.executor import assemble_evidence_package
from krakadyl.core.models import ProposedAction

OUT = Path(__file__).resolve().parent.parent / "out" / "case-001-muse"

MISSION_SUMMARY = (
    "Case case-001. Prepare the device-A evidence package for the "
    "authorized reviewer. Device B is out of scope and must stay excluded."
)
MANDATE_SUMMARY = (
    "Resource: case-001/device-A. Allowed operation: package_export. "
    "Allowed destination: reviewer-authorized. Device B is NOT covered."
)
CASE_SUMMARY = (
    "obs-a1, obs-a2: device-A, acquisition independently verified "
    "(VERIFIED_DONE). obs-b1: device-B, out of mandate scope regardless "
    "of verification status."
)


def main() -> None:
    api_key = os.environ.get("META_API_KEY")
    if not api_key:
        print("META_API_KEY not set (expected in .env). Nothing was called. Exiting.")
        return

    print("About to call Muse Spark (muse-spark-1.3, Standard mode) — this is a real, billed API call.")

    try:
        candidate = propose_action(
            mission_summary=MISSION_SUMMARY,
            mandate_summary=MANDATE_SUMMARY,
            case_summary=CASE_SUMMARY,
            api_key=api_key,
        )
    except MuseAdapterError as exc:
        print(f"Muse call failed or returned an invalid response: {exc}")
        return

    print("\n=== Muse's proposal (untrusted candidate, not yet authorized) ===")
    print(f"operation:      {candidate.operation}")
    print(f"allowed_device: {candidate.allowed_device}")
    print(f"destination:    {candidate.destination}")
    print(f"reasoning:      {candidate.reasoning}")

    if OUT.exists():
        shutil.rmtree(OUT)
    raw = OUT / "raw"
    raw.mkdir(parents=True)

    observations = [
        make_observation("obs-a1", "device-A", raw / "a1.jpg", b"device A photo one, authentic bytes"),
        make_observation("obs-a2", "device-A", raw / "a2.jpg", b"device A photo two, authentic bytes"),
        make_observation("obs-b1", "device-B", raw / "b1.jpg", b"device B photo one - must stay excluded"),
    ]
    files = {
        "obs-a1": raw / "a1.jpg",
        "obs-a2": raw / "a2.jpg",
        "obs-b1": raw / "b1.jpg",
    }
    requirements = [verified_requirement("obs-a1"), verified_requirement("obs-a2")]

    proposed_action = ProposedAction(
        id="action-muse-001",
        operation=candidate.operation,
        arguments={"device": candidate.allowed_device, "destination": candidate.destination},
        expected_effect=candidate.reasoning,
        mission_id="case-001",
    )

    decision, receipt = assemble_evidence_package(
        proposed_action=proposed_action,
        mandate=mandate(),
        observations=observations,
        requirements=requirements,
        observation_files=files,
        allowed_device=candidate.allowed_device,
        destination=candidate.destination,
        out_dir=OUT / "package",
        now=NOW,
    )
    report("Muse-generated action, checked by the deterministic engine", decision, receipt)
    print(f"\nAll output under: {OUT}")


if __name__ == "__main__":
    main()
