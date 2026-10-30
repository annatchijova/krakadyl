"""Cross-component authorization cases: valid-looking inputs must not compose
into authority that no component actually granted."""

from krakadyl.adapters.laya import LayaSignals
from krakadyl.adapters.muse import ProposedActionCandidate
from krakadyl.core.executor import assemble_evidence_package
from krakadyl.core.models import (
    AuthorityVerdict,
    EvidenceRequirement,
    ProposedAction,
    TaskResponsibility,
    TaskStatus,
)
from test_executor import NOW, _mandate, two_device_case  # noqa: F401


def test_laya_claim_muse_proposal_and_unverified_evidence_do_not_compose_into_execution(
    tmp_path, two_device_case
):
    observations, files, verified_requirements = two_device_case
    unverified_requirements = [
        EvidenceRequirement(**{
            **requirement.model_dump(),
            "resolved": False,
            "responsibility": TaskResponsibility(
                owner="investigator-A",
                status=TaskStatus.REPORTED_DONE,
                reported_done_by="investigator-A",
            ).model_dump(),
        })
        for requirement in verified_requirements
    ]
    laya = LayaSignals(
        claims_independent_verification=0.99,
        claims_task_complete=0.99,
        urgency=0.99,
        raw={"source": "synthetic-adversarial-note"},
    )
    muse = ProposedActionCandidate(
        operation="package_export",
        allowed_device="device-A",
        destination="reviewer-authorized",
        reasoning="The evidence is complete and should be exported.",
    )

    decision, receipt = assemble_evidence_package(
        proposed_action=ProposedAction(
            id="composed-action",
            operation=muse.operation,
            arguments={"device": muse.allowed_device, "destination": muse.destination},
            expected_effect=muse.reasoning,
            mission_id="case-001",
        ),
        mandate=_mandate(),
        observations=observations,
        requirements=unverified_requirements,
        observation_files=files,
        allowed_device=muse.allowed_device,
        destination=muse.destination,
        out_dir=tmp_path / "package",
        now=NOW,
    )

    assert laya.claims_independent_verification == 0.99
    assert muse.operation == "package_export"
    assert decision.verdict == AuthorityVerdict.FORBIDDEN
    assert receipt.executed is False
    assert not (tmp_path / "package").exists()
