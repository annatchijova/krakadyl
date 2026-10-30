"""The Level 3 lifecycle end to end, offline: open requirement -> route ->
proposal -> human authorization -> operator capture -> SAM derivation
(fake transport) -> evaluation -> requirement transition, through the
real SQLite gate, the real coordinator, and the real filesystem
repository. Only the network transport to Meta is replaced.

Passing these does not establish live SAM behavior; see
docs/level3-case-wiring.md for what the live closing run still needs.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from krakadyl.acquisition_runtime import (
    AcquisitionRuntime,
    AcquisitionUnavailable,
    CredentialRejected,
    FilesystemArtifactRepository,
    OperatorCredentials,
    hash_token,
    runtime_from_environment,
)
from krakadyl.adapters.sam import MetaSamProcessor
from krakadyl.core.acquisition import AcquisitionOutcomeUnknown, EvaluationOutcome, requirement_revision_digest
from krakadyl.core.continuity import evidence_state_from_requirement, find_urgent_discrepancies
from krakadyl.core.evaluation import (
    EvaluationRejected,
    abstain_requirement,
    acquisition_history,
    record_evaluation,
)
from krakadyl.core.models import (
    EvidenceRequirement,
    EvidenceState,
    Hypothesis,
    HypothesisStatus,
    Mandate,
    RecoveryWindow,
    RecoveryWindowKind,
    TaskResponsibility,
    TaskStatus,
)
from krakadyl.store import KrakadylStore

NOW = datetime.now(timezone.utc)
CASE = "case-001"
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic clock photograph"
SAM_TEXT = "<0f>1<|box;x1=2;y1=3;x2=10;y2=8;w=32;h=24;c=0.91|><|mask;x=0;y=0;data=2,3,~!!!!M|>"
TOKENS = {"investigator-A": "token-for-a", "investigator-C": "token-for-c"}


class _FakeSam:
    def __init__(self, text=SAM_TEXT, fail=False):
        self.text, self.fail, self.calls = text, fail, 0

    def __call__(self, url, headers, body, timeout):
        self.calls += 1
        if self.fail:
            raise ConnectionResetError("synthetic reset after dispatch")
        response = {"id": "sam-req-1", "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": self.text}]}]}
        return 200, {"x-request-id": "sam-req-1"}, json.dumps(response).encode()


def _requirement(**overrides):
    values = dict(
        id="req-device-a-clock",
        predicate="device-A's clock offset against reference time is established",
        acceptable_source_class="operator photograph",
        responsibility=TaskResponsibility(owner="investigator-A", status=TaskStatus.ASSIGNED),
        recovery_window=RecoveryWindow(
            kind=RecoveryWindowKind.CONDITIONAL,
            condition="device-A battery depletes",
            what_is_lost_if_missed="the live clock state at seizure",
        ),
        discriminating_question="Does device-A's on-screen clock match the reference clock within one minute?",
        answer_classes=["clock_matches_reference", "clock_offset_detected", "not_determinable"],
    )
    values.update(overrides)
    return EvidenceRequirement(**values)


HYPOTHESIS = Hypothesis(
    id="hyp-002",
    explanation="Device A's clock was correct at seizure.",
    status=HypothesisStatus.PROPOSED,
    discriminating_requirement_id="req-device-a-clock",
)


def _capture_mandate(**overrides):
    values = dict(
        id="mandate-capture-001",
        issuer="legal-authority-001",
        principal="investigator-A",
        resources=["case-001/operator-intake"],
        operations=["capture", "derive_annotation"],
        destinations=["local-only", "https://api.meta.ai/v1"],
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=5),
    )
    values.update(overrides)
    return Mandate(**values)


@pytest.fixture
def env(tmp_path):
    store = KrakadylStore(tmp_path / "k.db")
    store.put(CASE, "requirement", _requirement(), NOW.isoformat())
    store.put(CASE, "hypothesis", HYPOTHESIS, NOW.isoformat())
    store.put(CASE, "mandate", _capture_mandate(), NOW.isoformat())
    sam = _FakeSam()
    runtime = AcquisitionRuntime(
        store=store,
        credentials=OperatorCredentials.parse(";".join(f"{i}={hash_token(t)}" for i, t in TOKENS.items())),
        artifacts=FilesystemArtifactRepository(tmp_path / "acquired"),
        sam_processor=MetaSamProcessor(api_key="test-key", transport=sam),
    )
    yield store, runtime, sam, tmp_path
    store.close()


def _current(store):
    return store.get(CASE, "requirement", "req-device-a-clock", EvidenceRequirement)


def _proposal(store, runtime, sam_prompt="clock display"):
    return runtime.build_proposal(
        case_id=CASE,
        requirement=_current(store),
        hypotheses=[HYPOTHESIS],
        capture_mandate=_capture_mandate(),
        capture_instructions="Photograph device-A's lock screen beside the reference clock.",
        sam_prompt=sam_prompt,
        now=NOW,
    )


def _acquire(store, runtime, sam_prompt="clock display"):
    proposal = _proposal(store, runtime, sam_prompt)
    authorization = runtime.authorize(proposal, TOKENS["investigator-A"], NOW)
    return runtime.acquire(proposal, authorization, TOKENS["investigator-A"], PNG)


def _evaluate(store, result, evaluator, outcome, revision=None):
    return record_evaluation(
        store,
        case_id=CASE,
        workflow_id=result.workflow.workflow_id,
        expected_requirement_revision=revision or requirement_revision_digest(_current(store)),
        evaluator_identity=evaluator,
        criterion_id="clock-within-one-minute",
        criterion_version="1",
        outcome=outcome,
        rationale="Reference clock and device clock both read 16:42.",
        now=NOW,
    )


def test_independent_supporting_evaluation_resolves_requirement_and_never_touches_the_hypothesis(env):
    store, runtime, sam, tmp_path = env
    result = _acquire(store, runtime)

    assert result.annotation is not None and sam.calls == 1
    assert runtime.artifacts.read_verified(result.observation) == PNG
    assert runtime.artifacts.read_annotation(result.annotation) == SAM_TEXT.encode()
    # A convincing annotation alone changes nothing.
    assert _current(store) == _requirement()

    evaluation, updated = _evaluate(store, result, "investigator-C", EvaluationOutcome.SUPPORTS_REQUIREMENT)

    assert updated.resolved is True
    assert updated.responsibility.status == TaskStatus.VERIFIED_DONE
    assert updated.responsibility.verified_by == "investigator-C"
    assert updated.responsibility.reported_done_by == "investigator-A"
    assert evaluation.evaluation_id in updated.responsibility.verified_against
    assert evaluation.annotation_digest == result.annotation.output_digest
    assert evidence_state_from_requirement(updated) == EvidenceState.SUFFICIENT
    assert store.get(CASE, "hypothesis", "hyp-002", Hypothesis) == HYPOTHESIS

    history = acquisition_history(store, CASE)
    assert [h.state for h in history] == ["completed"]
    assert history[0].evaluations == [evaluation]
    assert [a.state for a in history[0].attempts] == ["completed", "completed"]


def test_self_evaluation_is_only_a_claim_until_someone_independent_evaluates(env):
    store, runtime, _, _ = env
    result = _acquire(store, runtime)

    _, claimed = _evaluate(store, result, "investigator-A", EvaluationOutcome.SUPPORTS_REQUIREMENT)
    assert claimed.resolved is False
    assert claimed.responsibility.status == TaskStatus.REPORTED_DONE
    assert evidence_state_from_requirement(claimed) == EvidenceState.MISSING
    assert [d.requirement_id for d in find_urgent_discrepancies([claimed], NOW)] == ["req-device-a-clock"]

    with pytest.raises(EvaluationRejected, match="already recorded"):
        _evaluate(store, result, "investigator-A", EvaluationOutcome.SUPPORTS_REQUIREMENT)

    _, verified = _evaluate(store, result, "investigator-C", EvaluationOutcome.SUPPORTS_REQUIREMENT)
    assert verified.resolved is True
    assert verified.responsibility.reported_done_by == "investigator-A"
    assert verified.responsibility.verified_by == "investigator-C"


@pytest.mark.parametrize(
    "outcome",
    [
        EvaluationOutcome.NO_DISCRIMINATING_CHANGE,
        EvaluationOutcome.INSUFFICIENT_OR_INVALID,
        EvaluationOutcome.CONTRADICTS_REQUIREMENT,
    ],
)
def test_non_supporting_outcomes_leave_the_requirement_open_and_a_new_route_available(env, outcome):
    store, runtime, sam, _ = env
    sam.text = ""  # valid, empty SAM result: no object found
    result = _acquire(store, runtime)
    assert result.annotation.is_empty is True

    _, after = _evaluate(store, result, "investigator-C", outcome)
    assert after == _requirement()

    second = _acquire(store, runtime, sam_prompt="analog clock face")
    assert second.workflow.workflow_id != result.workflow.workflow_id


def test_abstention_closes_the_requirement_honestly_and_flags_its_evaluations(env):
    store, runtime, sam, _ = env
    sam.text = ""
    result = _acquire(store, runtime)
    evaluation, _ = _evaluate(store, result, "investigator-C", EvaluationOutcome.NO_DISCRIMINATING_CHANGE)

    closed = abstain_requirement(
        store,
        case_id=CASE,
        requirement_id="req-device-a-clock",
        expected_requirement_revision=requirement_revision_digest(_current(store)),
        actor_identity="investigator-A",
        reason="device-A battery depleted before a readable capture",
        now=NOW,
    )
    assert closed.unresolvable is True
    assert evaluation.evaluation_id in closed.unresolvable_reason
    with pytest.raises(ValueError, match="no authorized acquisition route"):
        _proposal(store, runtime)


def test_stale_revision_is_refused_for_evaluation_and_abstention(env):
    store, runtime, _, _ = env
    result = _acquire(store, runtime)
    with pytest.raises(EvaluationRejected, match="changed since"):
        _evaluate(store, result, "investigator-C", EvaluationOutcome.SUPPORTS_REQUIREMENT, revision="0" * 64)
    with pytest.raises(EvaluationRejected, match="changed since"):
        abstain_requirement(
            store, case_id=CASE, requirement_id="req-device-a-clock",
            expected_requirement_revision="0" * 64, actor_identity="investigator-A",
            reason="x", now=NOW,
        )


def test_unknown_outcome_blocks_evaluation_abstention_and_new_acquisition(env):
    store, runtime, sam, _ = env
    sam.fail = True
    with pytest.raises(AcquisitionOutcomeUnknown):
        _acquire(store, runtime)
    history = acquisition_history(store, CASE)
    assert history[0].state == "unknown"
    assert history[0].observation is not None and history[0].annotation is None

    with pytest.raises(EvaluationRejected, match="not completed"):
        record_evaluation(
            store, case_id=CASE, workflow_id=history[0].workflow.workflow_id,
            expected_requirement_revision=requirement_revision_digest(_current(store)),
            evaluator_identity="investigator-C", criterion_id="c", criterion_version="1",
            outcome=EvaluationOutcome.SUPPORTS_REQUIREMENT, rationale="r", now=NOW,
        )
    with pytest.raises(EvaluationRejected, match="unknown outcome"):
        abstain_requirement(
            store, case_id=CASE, requirement_id="req-device-a-clock",
            expected_requirement_revision=requirement_revision_digest(_current(store)),
            actor_identity="investigator-A", reason="giving up", now=NOW,
        )
    sam.fail = False
    with pytest.raises(ValueError, match="active acquisition"):
        _acquire(store, runtime)
    assert sam.calls == 1


def test_unknown_token_cannot_authorize(env):
    store, runtime, _, _ = env
    with pytest.raises(CredentialRejected):
        runtime.authorize(_proposal(store, runtime), "guessed-token", NOW)


def test_identity_outside_the_capture_mandate_cannot_dispatch(env):
    store, runtime, sam, tmp_path = env
    proposal = _proposal(store, runtime)
    authorization = runtime.authorize(proposal, TOKENS["investigator-C"], NOW)
    with pytest.raises(ValueError, match="scoped to 'investigator-A'"):
        runtime.acquire(proposal, authorization, TOKENS["investigator-C"], PNG)
    assert sam.calls == 0
    assert acquisition_history(store, CASE) == []
    assert not (tmp_path / "acquired").exists()


def test_a_different_token_cannot_spend_someone_elses_authorization(env):
    store, runtime, sam, _ = env
    proposal = _proposal(store, runtime)
    authorization = runtime.authorize(proposal, TOKENS["investigator-A"], NOW)
    with pytest.raises(ValueError, match="does not match the grant authorizer"):
        runtime.acquire(proposal, authorization, TOKENS["investigator-C"], PNG)
    assert acquisition_history(store, CASE) == []


def test_authorization_is_single_use(env):
    store, runtime, sam, _ = env
    proposal = _proposal(store, runtime, sam_prompt=None)
    authorization = runtime.authorize(proposal, TOKENS["investigator-A"], NOW)
    runtime.acquire(proposal, authorization, TOKENS["investigator-A"], PNG)
    with pytest.raises(ValueError, match="already used|stale|already has"):
        runtime.acquire(proposal, authorization, TOKENS["investigator-A"], PNG)
    assert len(acquisition_history(store, CASE)) == 1


def test_requirement_changed_after_approval_makes_the_approval_stale(env):
    store, runtime, sam, _ = env
    proposal = _proposal(store, runtime)
    authorization = runtime.authorize(proposal, TOKENS["investigator-A"], NOW)
    store.put(CASE, "requirement", _requirement(discriminating_question="Is the clock roughly right?"), NOW.isoformat())
    with pytest.raises(ValueError, match="stale"):
        runtime.acquire(proposal, authorization, TOKENS["investigator-A"], PNG)
    assert sam.calls == 0


def test_capture_only_proposal_has_no_processing_and_no_spend(env):
    store, runtime, sam, _ = env
    result = _acquire(store, runtime, sam_prompt=None)
    assert result.annotation is None
    assert sam.calls == 0
    assert result.workflow.actual_usage.usd_micros == 0


def test_non_image_upload_is_rejected_before_any_state_changes(env):
    store, runtime, sam, _ = env
    proposal = _proposal(store, runtime)
    authorization = runtime.authorize(proposal, TOKENS["investigator-A"], NOW)
    with pytest.raises(ValueError, match="PNG or JPEG"):
        runtime.acquire(proposal, authorization, TOKENS["investigator-A"], b"%PDF-1.7 not an image")
    assert acquisition_history(store, CASE) == []


def test_tampered_artifact_fails_read_time_verification(env):
    store, runtime, _, tmp_path = env
    result = _acquire(store, runtime, sam_prompt=None)
    path = tmp_path / "acquired" / CASE / "originals" / result.observation.digest
    path.write_bytes(b"\x89PNG\r\n\x1a\nswapped")
    with pytest.raises(ValueError, match="digest verification"):
        runtime.artifacts.read_verified(result.observation)


def test_sam_prompt_is_refused_when_sam_is_not_enabled(env):
    store, runtime, _, tmp_path = env
    capture_only = AcquisitionRuntime(
        store=store, credentials=runtime.credentials,
        artifacts=FilesystemArtifactRepository(tmp_path / "other"),
    )
    with pytest.raises(AcquisitionUnavailable):
        _proposal(store, capture_only)


def test_environment_fails_closed(tmp_path, monkeypatch):
    store = KrakadylStore(tmp_path / "e.db")
    monkeypatch.delenv("KRAKADYL_OPERATOR_TOKENS", raising=False)
    assert runtime_from_environment(store, tmp_path) is None

    monkeypatch.setenv("KRAKADYL_OPERATOR_TOKENS", f"investigator-A={hash_token('t')}")
    monkeypatch.setenv("KRAKADYL_ENABLE_SAM", "1")
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="META_API_KEY"):
        runtime_from_environment(store, tmp_path)

    monkeypatch.setenv("META_API_KEY", "k")
    monkeypatch.delenv("KRAKADYL_ENABLE_SAM")
    assert runtime_from_environment(store, tmp_path).sam_enabled is False
    store.close()


def test_credential_configuration_holds_hashes_only():
    with pytest.raises(ValueError):
        OperatorCredentials.parse("investigator-A=plaintext-token")
    with pytest.raises(ValueError):
        OperatorCredentials.parse(f"a={hash_token('same')};b={hash_token('same')}")
