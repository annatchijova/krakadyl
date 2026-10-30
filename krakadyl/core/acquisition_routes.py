"""Which open requirements an authorized source could still resolve.

This is the bridge between the case state (requirements, hypotheses,
mandates) and the acquisition contract in `acquisition.py`. It answers
one question deterministically — "is there an authorized, discriminating
capture route for this requirement right now?" — and builds the
`AcquisitionNeedSnapshot` a proposal must carry. It never proposes,
authorizes, or dispatches anything: a route is a fact the policy engine
and the UI can read, not permission.

A route exists only when every one of these holds, and the refusal
names the first that does not:

- the requirement is open (not resolved, not unresolvable, not blocked);
- it states a discriminating question with at least two answer classes;
- at least one hypothesis names it as its discriminating requirement;
- a registered source serves exactly its `acceptable_source_class`;
- a current capture mandate grants `capture` on that source's resource.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from krakadyl.core.acquisition import (
    AcquisitionNeedSnapshot,
    need_state_digest,
    requirement_revision_digest,
)
from krakadyl.core.executor import check_mandate
from krakadyl.core.models import AuthorityState, EvidenceRequirement, Hypothesis, Mandate

CAPTURE_OPERATION = "capture"
DERIVE_OPERATION = "derive_annotation"
LOCAL_DESTINATION = "local-only"


class SourceCapability(BaseModel):
    """A source this deployment can actually acquire from, declared by
    configuration — never inferred from a model's suggestion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9._-]+$")
    capability_version: str = Field(min_length=1)
    source_class: str = Field(min_length=1)
    description: str = Field(min_length=1)

    def resource_for(self, case_id: str) -> str:
        return f"{case_id}/{self.source_id}"


class AcquisitionRoute(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str
    source_id: str
    source_capability_version: str
    resource: str
    mandate_id: str
    mandate_revision: str
    question: str
    answer_classes: tuple[str, ...]
    hypothesis_ids: tuple[str, ...]


class RouteRefusal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str
    reason: str


def linked_hypotheses(requirement: EvidenceRequirement, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Every hypothesis this requirement discriminates, in id order — the
    exact set and order the gate recomputes inside its transaction."""
    return sorted(
        (h for h in hypotheses if h.discriminating_requirement_id == requirement.id),
        key=lambda h: h.id,
    )


def acquisition_route(
    *,
    case_id: str,
    requirement: EvidenceRequirement,
    hypotheses: list[Hypothesis],
    capture_mandate: Optional[Mandate],
    sources: list[SourceCapability],
    now: datetime,
) -> AcquisitionRoute | RouteRefusal:
    def refuse(reason: str) -> RouteRefusal:
        return RouteRefusal(requirement_id=requirement.id, reason=reason)

    if requirement.resolved:
        return refuse("requirement is already resolved")
    if requirement.unresolvable:
        return refuse(f"requirement was closed as unresolvable: {requirement.unresolvable_reason}")
    if requirement.blocked_by_authority:
        return refuse(requirement.blocked_reason or "requirement is blocked by authority")
    if not requirement.discriminating_question or len(requirement.answer_classes) < 2:
        return refuse("requirement states no discriminating question with answer classes")
    linked = linked_hypotheses(requirement, hypotheses)
    if not linked:
        return refuse("no hypothesis depends on this requirement, so a capture would discriminate nothing")
    matching = [s for s in sources if s.source_class == requirement.acceptable_source_class]
    if not matching:
        return refuse(f"no configured source serves '{requirement.acceptable_source_class}'")
    if capture_mandate is None:
        return refuse("case has no capture mandate")
    if len(matching) > 1:
        # Choosing between sources is a human decision with its own
        # tradeoffs; picking the first one silently would not be.
        return refuse("more than one configured source serves this class; no single route is defensible")
    source = matching[0]
    check = check_mandate(
        capture_mandate,
        resource=source.resource_for(case_id),
        operation=CAPTURE_OPERATION,
        destination=LOCAL_DESTINATION,
        now=now,
    )
    if check.outside_scope or check.authority_state != AuthorityState.GRANTED:
        return refuse("capture mandate does not currently grant this source: " + "; ".join(check.reasons))
    return AcquisitionRoute(
        requirement_id=requirement.id,
        source_id=source.source_id,
        source_capability_version=source.capability_version,
        resource=source.resource_for(case_id),
        mandate_id=capture_mandate.id,
        mandate_revision=capture_mandate.revision,
        question=requirement.discriminating_question,
        answer_classes=tuple(requirement.answer_classes),
        hypothesis_ids=tuple(h.id for h in linked),
    )


def resolvable_requirement_ids(
    *,
    case_id: str,
    requirements: list[EvidenceRequirement],
    hypotheses: list[Hypothesis],
    capture_mandate: Optional[Mandate],
    sources: list[SourceCapability],
    now: datetime,
) -> frozenset[str]:
    return frozenset(
        r.id
        for r in requirements
        if isinstance(
            acquisition_route(
                case_id=case_id,
                requirement=r,
                hypotheses=hypotheses,
                capture_mandate=capture_mandate,
                sources=sources,
                now=now,
            ),
            AcquisitionRoute,
        )
    )


def need_snapshot_for(
    *, case_id: str, requirement: EvidenceRequirement, hypotheses: list[Hypothesis]
) -> AcquisitionNeedSnapshot:
    linked = linked_hypotheses(requirement, hypotheses)
    if not requirement.discriminating_question:
        raise ValueError("requirement states no discriminating question")
    return AcquisitionNeedSnapshot(
        case_id=case_id,
        requirement_id=requirement.id,
        requirement_revision=requirement_revision_digest(requirement),
        hypothesis_ids=tuple(h.id for h in linked),
        question=requirement.discriminating_question,
        answer_classes=tuple(requirement.answer_classes),
        need_state_digest=need_state_digest(requirement, linked),
    )
