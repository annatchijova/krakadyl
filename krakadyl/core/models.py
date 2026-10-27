"""Domain contracts for KRAKADYL — Level 1.

Custody (owner + claimed-vs-verified) and the evidence/authority dual
state are present on every object that can be "done" by someone, per
docs/levels.md invariant 4: nothing defaults to "someone probably did
this already."
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Full lifecycle of a piece of investigative work.

    UNASSIGNED -> ASSIGNED -> ACKNOWLEDGED -> IN_PROGRESS -> REPORTED_DONE
    -> VERIFIED_DONE is the expected happy path. BLOCKED/EXPIRED/
    CANCELLED/UNKNOWN exist because real investigations have those
    outcomes too, and a status enum that can't represent them gets
    abused to represent them anyway.

    Three things this status machine refuses to do, on purpose:
    - ASSIGNED is not ACKNOWLEDGED. Handing a task to someone is not the
      same fact as that person having taken responsibility for it —
      assigning without an explicit, separate acknowledgment is exactly
      how "I thought he had it" happens. This is a distinct enum value,
      not a side timestamp, so "how many tasks are assigned but nobody
      has acknowledged yet" is a direct query, not something that
      requires remembering to check a field.
    - REPORTED_DONE is never read as VERIFIED_DONE by anything
      downstream (see continuity.py::evidence_state_from_requirement).
      "Someone said they did it" and "it's verified" are different
      states, not different labels for the same state.
    - Neither of the above ever collapses back into UNASSIGNED or
      "unknown." A reported-but-unverified claim is uncertainty that
      gets preserved as its own state, not information that gets
      discarded because it wasn't confirmed. See
      docs/terminal-first-and-blame.md and docs/levels.md for why.
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


class Custody(BaseModel):
    """Who owns a piece of work, who accepted it, and its real status.

    Embedded in every object a person or the agent can mark "done," so
    "done" never means more than what this field actually says.
    """

    owner: str
    status: TaskStatus
    assigned_at: Optional[datetime] = None
    accepted_by: Optional[str] = None
    accepted_at: Optional[datetime] = None
    reported_done_by: Optional[str] = None
    reported_done_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    due_at: Optional[datetime] = None

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


class Mandate(BaseModel):
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
    custody: Custody


class Claim(BaseModel):
    id: str
    statement: str
    supporting_observation_ids: list[str] = Field(default_factory=list)
    epistemic_status: str  # e.g. "asserted" | "corroborated" | "contradicted"
    verification_method: Optional[str] = None
    custody: Custody


class RecoveryWindow(BaseModel):
    """Whether, and how, this evidence could still be lost irreversibly.

    The six questions that matter, made explicit fields instead of left
    to be inferred: until when can it be obtained, what hypotheses need
    it, what's uncertain about its relevance, what it costs to acquire,
    and what's lost if it's missed. Authority ("is it allowed now") is
    deliberately NOT a field here — it comes from Decision/decide(), so
    there is exactly one place that fact lives, not two that could
    disagree.
    """

    until: Optional[datetime] = None  # None: no known expiry
    what_is_lost_if_missed: str
    acquisition_cost: Optional[str] = None
    depends_on_hypothesis_ids: list[str] = Field(default_factory=list)
    uncertainty_note: Optional[str] = None


class EvidenceRequirement(BaseModel):
    id: str
    predicate: str
    acceptable_source_class: str
    freshness_requirement: Optional[str] = None
    resolved: bool = False
    unresolvable: bool = False
    unresolvable_reason: Optional[str] = None
    recovery_window: Optional[RecoveryWindow] = None
    blocked_by_authority: bool = False
    blocked_reason: Optional[str] = None
    custody: Custody


class Hypothesis(BaseModel):
    id: str
    explanation: str
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


class PreparedAction(BaseModel):
    id: str
    proposed_action_id: str
    payload_digest: str
    destination: str
    resources_touched: list[str]
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
