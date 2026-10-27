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


class CustodyStatus(str, Enum):
    """Whether a claimed piece of work has been independently verified.

    CLAIMED is the only state anyone can set by saying "I did it."
    VERIFIED requires evidence attached — a second observation, a
    signature, a tool's own confirmation. The two are never conflated.
    """

    CLAIMED = "claimed"
    VERIFIED = "verified"


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
    """Who owns a piece of work, and whether it's claimed or verified.

    Embedded in every object a person or the agent can mark "done," so
    "done" never means more than what this field actually says.
    """

    owner: str
    status: CustodyStatus
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None


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


class EvidenceRequirement(BaseModel):
    id: str
    predicate: str
    acceptable_source_class: str
    freshness_requirement: Optional[str] = None
    resolved: bool = False
    unresolvable: bool = False
    unresolvable_reason: Optional[str] = None
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
