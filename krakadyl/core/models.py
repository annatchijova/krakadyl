"""Domain contracts for KRAKADYL — Level 1.

Two things are present on every object that can be "done" or "held" by
someone, per docs/levels.md invariant 4: nothing defaults to "someone
probably did this already," and task responsibility is never conflated
with evidence custody — they are different concepts, tracked separately
(correction from the Oct 27 review: a completed task does not, by
itself, demonstrate custody of its result).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskStatus(str, Enum):
    """Full lifecycle of a piece of investigative work.

    UNASSIGNED -> ASSIGNED -> ACKNOWLEDGED -> IN_PROGRESS -> REPORTED_DONE
    -> VERIFIED_DONE is the expected happy path. BLOCKED/EXPIRED/
    CANCELLED/UNKNOWN exist because real investigations have those
    outcomes too, and a status enum that can't represent them gets
    abused to represent them anyway.

    Enforced today in the one place that currently sets this state
    (TaskResponsibility itself, via the validator below) — not yet
    proven against every possible mutation path, persistence, or
    serialization, which is still open work:
    - ASSIGNED is not ACKNOWLEDGED. Handing a task to someone is not the
      same fact as that person having taken responsibility for it.
    - REPORTED_DONE is never read as VERIFIED_DONE by anything
      downstream (see continuity.py::evidence_state_from_requirement).
    - Neither collapses back into UNASSIGNED or "unknown" — a
      reported-but-unverified claim is uncertainty that gets preserved
      as its own state. See docs/terminal-first-and-blame.md.
    """

    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    REPORTED_DONE = "reported_done"
    VERIFIED_DONE = "verified_done"
    BLOCKED = "blocked"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class EvidenceState(str, Enum):
    SUFFICIENT = "sufficient"
    MISSING = "missing"
    CONFLICTING = "conflicting"
    STALE = "stale"


class AuthorityState(str, Enum):
    GRANTED = "granted"
    NEEDS_CONSENT = "needs_consent"
    DENIED = "denied"
    EXPIRED = "expired"


class AuthorityVerdict(str, Enum):
    ALLOWED = "allowed"
    CONFIRM = "confirm"
    GATHER_EVIDENCE = "gather_evidence"
    FORBIDDEN = "forbidden"


class TaskResponsibility(BaseModel):
    """Who owns a piece of WORK, who accepted it, and its real status.

    This is about tasks — assignment, acceptance, execution of a step —
    not about evidence. See EvidenceCustody below for the chain-of-
    custody concept this used to be conflated with (renamed from
    `Custody` on 2026-10-27, per the Oct 27 review: completing a task
    does not, by itself, demonstrate custody of whatever it produced).

    `validate_assignment=True` — found by self-red-teaming the Level 2
    build: without it, `resp.status = TaskStatus.VERIFIED_DONE` after
    construction bypassed the independent-verification validator below
    entirely (Pydantic only runs validators at construction by default).
    Reproduced, then fixed here — the earlier claim that this was
    "enforced at construction time" was true but incomplete.
    """

    model_config = ConfigDict(validate_assignment=True)

    owner: str
    status: TaskStatus
    assigned_at: Optional[datetime] = None
    accepted_by: Optional[str] = None
    accepted_at: Optional[datetime] = None
    reported_done_by: Optional[str] = None
    reported_done_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    verification_method: Optional[str] = None
    verified_against: Optional[str] = None
    due_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _verified_done_requires_independent_verification(self) -> "TaskResponsibility":
        """Reaching VERIFIED_DONE must record what was checked, how, and
        that the check was independent of whoever reported it done.

        "Independent" doesn't require a second human — it requires the
        verifier not to be the same act of self-report. A verification_
        method prefixed "tool:" (an automated, separate-from-the-agent
        check) counts as independent even if verified_by happens to
        equal reported_done_by; anything else needs a different actor.
        """
        if self.status != TaskStatus.VERIFIED_DONE:
            return self
        if not self.verified_by or not self.verification_method:
            raise ValueError(
                "VERIFIED_DONE requires verified_by and verification_method — "
                "a status label alone is not a verification"
            )
        is_automated_check = self.verification_method.startswith("tool:")
        if not is_automated_check and self.verified_by == self.reported_done_by:
            raise ValueError(
                "VERIFIED_DONE requires independent verification: verified_by "
                "must differ from reported_done_by, or verification_method "
                "must denote an automated check (prefixed 'tool:')"
            )
        return self

    @property
    def is_verified(self) -> bool:
        return self.status == TaskStatus.VERIFIED_DONE

    @property
    def is_only_claimed(self) -> bool:
        """True exactly when someone said it's done but nothing verified it.

        This is the condition the mandatory adversarial scenario (see
        docs/levels.md) hinges on: an investigator reports a volatile
        source preserved, a teammate closes the task, and the system
        must be able to ask this question and get True.
        """
        return self.status == TaskStatus.REPORTED_DONE


class CustodyTransfer(BaseModel):
    from_holder: str
    to_holder: str
    at: datetime
    method: Optional[str] = None


class CustodyTransformation(BaseModel):
    operation: str
    performed_by: str
    at: datetime
    resulting_digest: Optional[str] = None


class EvidenceCustody(BaseModel):
    """Chain of custody for an artifact — a different concept from
    TaskResponsibility. Acquisition, who has held it, what was done to
    it, and whether its integrity is checked, independent of whether
    any particular task tracking it is marked done.
    """

    acquired_by: str
    acquired_at: datetime
    acquisition_method: str
    possessors: list[CustodyTransfer] = Field(default_factory=list)
    transformations: list[CustodyTransformation] = Field(default_factory=list)
    integrity_digest: Optional[str] = None
    integrity_verified: bool = False
    integrity_verified_by: Optional[str] = None


class Mandate(BaseModel):
    """Mandates are immutable snapshots, not mutated in place — a change
    (new resources, revocation, a tightened scope) is a NEW Mandate
    object with a bumped `revision`. This is what Level 2's invalidation
    engine compares a PreparedAction's `mandate_revision_checked`
    against, to catch "this was approved under a mandate that no longer
    exists in that form."

    `frozen=True` — found by self-red-teaming the Level 2 build: without
    it, `mandate.revoked = True` silently mutated an existing Mandate
    without bumping `revision`, which would have silently defeated the
    invalidation engine (it compares revision strings, not field
    contents). Reproduced, then fixed here. A caller that needs to
    change a Mandate must now construct a new one — which is the only
    way `revision` gets a chance to be bumped honestly.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    issuer: str
    principal: str
    resources: list[str]
    operations: list[str]
    destinations: list[str]
    valid_from: datetime
    valid_until: Optional[datetime] = None
    revoked: bool = False
    revoked_reason: Optional[str] = None
    revision: str = "1"


class Mission(BaseModel):
    id: str
    objective: str
    domain: str
    mandate_id: str
    termination_criteria: str
    created_at: datetime


class Observation(BaseModel):
    id: str
    source: str
    digest: str
    captured_at: datetime
    event_time: Optional[datetime] = None
    actor: str
    visual_region: Optional[str] = None
    evidence_custody: EvidenceCustody
    invalidated: bool = False
    invalidation_reason: Optional[str] = None

    @model_validator(mode="after")
    def _invalidation_has_a_reason(self) -> "Observation":
        if self.invalidated and not self.invalidation_reason:
            raise ValueError("an invalidated observation needs a reason")
        if not self.invalidated and self.invalidation_reason is not None:
            raise ValueError("an invalidation reason requires invalidated=True")
        return self


class VerificationBasis(BaseModel):
    """A typed source used by one verification, never a prose citation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str = Field(min_length=1)
    observation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class VerificationRecord(BaseModel):
    """One verification and the primary observations it actually relied on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verification_id: str = Field(min_length=1)
    verifier_identity: str = Field(min_length=1)
    target_observation_id: str = Field(min_length=1)
    basis: tuple[VerificationBasis, ...] = Field(min_length=1)
    parent_verification_ids: tuple[str, ...] = ()
    method: str = Field(min_length=1, max_length=256)
    recorded_at: datetime

    @model_validator(mode="after")
    def _basis_is_unique_and_timed(self) -> "VerificationRecord":
        if self.recorded_at.utcoffset() is None:
            raise ValueError("verification timestamp must include a timezone")
        ids = [item.observation_id for item in self.basis]
        if len(set(ids)) != len(ids):
            raise ValueError("verification basis observations must be unique")
        if self.verification_id in self.parent_verification_ids:
            raise ValueError("a verification cannot depend on itself")
        if len(set(self.parent_verification_ids)) != len(self.parent_verification_ids):
            raise ValueError("parent verification IDs must be unique")
        return self


class Claim(BaseModel):
    id: str
    statement: str
    supporting_observation_ids: list[str] = Field(default_factory=list)
    epistemic_status: str  # e.g. "asserted" | "corroborated" | "contradicted"
    verification_method: Optional[str] = None
    responsibility: TaskResponsibility


class RecoveryWindowKind(str, Enum):
    KNOWN = "known"  # a concrete, confirmed deadline
    ESTIMATED = "estimated"  # a deadline inferred from a stated basis, not confirmed
    CONDITIONAL = "conditional"  # closes when an event happens, timing unknown
    UNKNOWN = "unknown"  # genuinely no information — not the same as "no risk"


class RecoveryWindow(BaseModel):
    """Whether, and how, this evidence could still be lost irreversibly.

    The six questions that matter, made explicit fields instead of left
    to be inferred: until when (if known or estimated) or under what
    condition (if event-triggered) can it be obtained, what hypotheses
    need it, what's uncertain about its relevance, what it costs to
    acquire, and what's lost if it's missed. Authority ("is it allowed
    now") is deliberately NOT a field here — it comes from
    Decision/decide(), so there is exactly one place that fact lives.

    `kind` exists because "no known expiry" (UNKNOWN) and "closes when
    the device powers off, timing unknown" (CONDITIONAL) are different
    situations that a single optional `until` datetime cannot represent
    without silently treating both as "not urgent" — correction from
    the Oct 27 review.

    `validate_assignment=True` for the same reason as TaskResponsibility:
    without it, `kind`/`until`/`condition` could be reassigned post-
    construction without re-checking `_kind_matches_fields`, silently
    producing an internally inconsistent window.
    """

    model_config = ConfigDict(validate_assignment=True)

    kind: RecoveryWindowKind = RecoveryWindowKind.UNKNOWN
    until: Optional[datetime] = None
    estimate_basis: Optional[str] = None
    condition: Optional[str] = None
    what_is_lost_if_missed: str
    acquisition_cost: Optional[str] = None
    depends_on_hypothesis_ids: list[str] = Field(default_factory=list)
    uncertainty_note: Optional[str] = None

    @model_validator(mode="after")
    def _kind_matches_fields(self) -> "RecoveryWindow":
        if self.kind in (RecoveryWindowKind.KNOWN, RecoveryWindowKind.ESTIMATED):
            if self.until is None:
                raise ValueError(f"'{self.kind.value}' recovery window requires 'until'")
        if self.kind == RecoveryWindowKind.ESTIMATED and not self.estimate_basis:
            raise ValueError(
                "estimated recovery window requires estimate_basis "
                "(the source and confidence behind the estimate)"
            )
        if self.kind == RecoveryWindowKind.CONDITIONAL and not self.condition:
            raise ValueError(
                "conditional recovery window requires 'condition' "
                "(the event that closes it, e.g. 'device power-off')"
            )
        return self


class EvidenceRequirement(BaseModel):
    """`resolved` and `unresolvable` are deliberately mutually exclusive
    — found contradictory (both True at once, meaning "resolved AND
    permanently unresolvable" simultaneously) while self-red-teaming
    the Level 2 build. Reproduced, then fixed with the validator below.
    """

    model_config = ConfigDict(validate_assignment=True)

    id: str
    predicate: str
    acceptable_source_class: str
    freshness_requirement: Optional[str] = None
    # Which Observation this requirement's custody lifecycle governs —
    # the link executor.py uses to refuse packaging an observation
    # whose acquisition was never independently verified, added
    # 2026-10-27 to close the cross-module gap found by self-red-teaming
    # (the executor used to check file integrity only, never custody).
    observation_id: Optional[str] = None
    resolved: bool = False
    unresolvable: bool = False
    unresolvable_reason: Optional[str] = None
    recovery_window: Optional[RecoveryWindow] = None
    blocked_by_authority: bool = False
    blocked_reason: Optional[str] = None
    responsibility: TaskResponsibility
    # Structured provenance is optional for legacy records while the
    # verification graph is being introduced. When present, execution
    # validates every source and rejects shared primary ancestry.
    verification_records: tuple[VerificationRecord, ...] = ()
    # Level 3: the question a new capture would have to answer, and the
    # categorical answers that would discriminate between hypotheses.
    # Without both, no acquisition can be proposed for this requirement
    # — "go get more evidence" with no stated question is exactly the
    # non-discriminating capture docs/level3-acquisition-contracts.md
    # forbids. Part of the requirement itself (not a side record) so the
    # acquisition need-state digest covers it: rewording the question
    # after a human approved a capture makes that approval stale.
    discriminating_question: Optional[str] = None
    answer_classes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _resolved_and_unresolvable_are_exclusive(self) -> "EvidenceRequirement":
        if self.resolved and self.unresolvable:
            raise ValueError(
                "a requirement cannot be both 'resolved' and 'unresolvable' — "
                "these are mutually exclusive outcomes"
            )
        return self

    @model_validator(mode="after")
    def _verification_records_are_independent(self) -> "EvidenceRequirement":
        if not self.verification_records:
            return self
        if self.observation_id is None:
            raise ValueError("structured verification records require an observation_id")
        if len({record.verification_id for record in self.verification_records}) != len(self.verification_records):
            raise ValueError("verification record IDs must be unique")
        records_by_id = {record.verification_id: record for record in self.verification_records}
        for record in self.verification_records:
            if any(parent not in records_by_id for parent in record.parent_verification_ids):
                raise ValueError("verification record references an unknown parent")
        if len({record.verifier_identity for record in self.verification_records}) != len(self.verification_records):
            raise ValueError("independent verification records require distinct verifiers")
        referenced_ids = {
            parent
            for record in self.verification_records
            for parent in record.parent_verification_ids
        }
        roots = [record for record in self.verification_records if record.verification_id not in referenced_ids]
        if not roots or any(record.target_observation_id != self.observation_id for record in roots):
            raise ValueError("verification graph root targets a different observation")
        for record in self.verification_records:
            if any(basis.observation_id == record.target_observation_id for basis in record.basis):
                raise ValueError("target observation cannot be a verification source")
        observation_dependencies: dict[str, set[str]] = {}
        for record in self.verification_records:
            observation_dependencies.setdefault(record.target_observation_id, set()).update(
                basis.observation_id for basis in record.basis
            )
        visiting_observations: set[str] = set()
        visited_observations: set[str] = set()

        def visit_observation(observation_id: str) -> None:
            if observation_id in visiting_observations:
                raise ValueError("observation dependency graph contains a cycle")
            if observation_id in visited_observations:
                return
            visiting_observations.add(observation_id)
            for dependency_id in observation_dependencies.get(observation_id, set()):
                visit_observation(dependency_id)
            visiting_observations.remove(observation_id)
            visited_observations.add(observation_id)

        for observation_id in observation_dependencies:
            visit_observation(observation_id)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(record_id: str) -> None:
            if record_id in visiting:
                raise ValueError("verification dependency graph contains a cycle")
            if record_id in visited:
                return
            visiting.add(record_id)
            for parent in records_by_id[record_id].parent_verification_ids:
                visit(parent)
            visiting.remove(record_id)
            visited.add(record_id)

        for record in self.verification_records:
            visit(record.verification_id)
        for index, first in enumerate(roots):
            first_sources = {item.observation_id for item in first.basis}
            for second in roots[index + 1:]:
                shared = first_sources.intersection(item.observation_id for item in second.basis)
                if shared:
                    raise ValueError(
                        "independent verification records share a primary source: "
                        + ", ".join(sorted(shared))
                    )
        return self

    @model_validator(mode="after")
    def _question_and_answer_classes_come_together(self) -> "EvidenceRequirement":
        if self.discriminating_question is None and not self.answer_classes:
            return self
        if not self.discriminating_question or not self.discriminating_question.strip():
            raise ValueError("answer classes require a non-empty discriminating question")
        if len(self.answer_classes) < 2 or len(set(self.answer_classes)) != len(self.answer_classes):
            raise ValueError(
                "a discriminating question needs at least two distinct answer classes — "
                "a question with one possible answer discriminates nothing"
            )
        return self


class HypothesisStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Hypothesis(BaseModel):
    """`status` was a plain, unvalidated string until self-red-teaming
    the Level 2 build showed it accepted any value (a typo or case
    mismatch would silently fail to match the 'rejected' check in
    invalidation.py::find_hypotheses_needing_review). Now a real enum,
    validated on assignment too, for the same reason TaskResponsibility
    and RecoveryWindow got validate_assignment=True.
    """

    model_config = ConfigDict(validate_assignment=True)

    id: str
    explanation: str
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    discriminating_requirement_id: Optional[str] = None


class ProposedAction(BaseModel):
    id: str
    operation: str
    arguments: dict
    depends_on_requirement_ids: list[str] = Field(default_factory=list)
    expected_effect: str
    mission_id: str


class ExclusionRecord(BaseModel):
    """Why one specific resource is absent from a package, distinct from
    `excluded_sources` (a whole device outside the mandate, which needs
    no cause — it was simply never in scope). Found missing by
    self-red-teaming Level 2's recovery mechanism (2026-10-27): a
    resource dropped because its integrity check failed or its
    acquisition was never independently verified is a materially
    different fact from "never in scope," and a forensic package must
    be able to answer "why isn't this item here," not just omit it
    silently the same way an out-of-scope device is omitted.
    """

    model_config = ConfigDict(frozen=True)

    resource_id: str
    reason: str


class PreparedAction(BaseModel):
    """A frozen snapshot of 'this is safe to do, checked against this
    revision of the mandate and these resource digests' — frozen=True
    so nothing downstream can mutate `resources_touched`,
    `source_revision_checked`, etc. after the fact to make a stale
    action look current again. Found missing by self-red-teaming the
    Level 2 build; a mutable "snapshot" is not a snapshot.

    `resources_touched`/`excluded_sources` are `tuple[str, ...]`, not
    `list[str]` — found by the Oct 27 follow-up review: `frozen=True`
    only blocks field *reassignment* (`prepared.x = y`), it does not
    deep-freeze a mutable field's contents, so
    `prepared.resources_touched.append(...)` silently succeeded despite
    the model being "frozen." A tuple has no `.append` to bypass with.

    `resource` is the exact resource string checked against the mandate
    at prepare time (e.g. `"case-001/device-A"`) — stored so
    `execute_prepared_action` can re-run the *full* mandate check
    (scope, validity window, revocation) against it, not just compare
    revision strings.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    proposed_action_id: str
    payload_digest: str
    resource: str
    operation: str
    destination: str
    resources_touched: tuple[str, ...]
    # (observation_id, requirement_id, full requirement revision at prepare)
    # binds the evidence decision to the exact verification basis that made
    # it sufficient; a later VERIFIED_DONE label is not enough by itself.
    requirement_revisions: tuple[tuple[str, str, str], ...] = ()
    excluded_sources: tuple[str, ...] = ()
    excluded_resource_reasons: tuple[ExclusionRecord, ...] = ()
    source_revision_checked: str
    mandate_revision_checked: str
    expires_at: datetime
    nonce: str


class Decision(BaseModel):
    id: str
    proposed_action_id: str
    verdict: AuthorityVerdict
    evidence_state: EvidenceState
    authority_state: AuthorityState
    reasons: list[str]
    supporting_refs: list[str] = Field(default_factory=list)
    decided_at: datetime


class Receipt(BaseModel):
    id: str
    proposed_action_id: str
    decision_id: str
    executed: bool
    observed_effect: Optional[str] = None
    uncertain_outcome: bool = False
    prev_hash: Optional[str] = None
    hash: str
    created_at: datetime
