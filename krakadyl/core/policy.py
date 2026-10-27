"""Deterministic policy engine.

Decides over (evidence_state, authority_state) and two independent
facts: whether an authorized source could still resolve missing
evidence, and whether the action is categorically outside the mandate.
Never over a model's or Laya's interpretation directly — those are
inputs that get turned into these typed facts by the caller before this
function ever runs.

Order of precedence, from docs/levels.md / the Oct 26 design notes:
outside the mandate, full stop -> FORBIDDEN, no exceptions below it.
decision belongs to the person -> CONFIRM.
missing/conflicting/stale evidence but a legitimate source could still
resolve it -> GATHER_EVIDENCE.
otherwise, sufficient evidence and granted authority -> ALLOWED.
Anything that reaches the end without matching a rule is denied by
default — the safe default is "don't execute," not "ask."
"""

from __future__ import annotations

from krakadyl.core.models import AuthorityState, AuthorityVerdict, EvidenceState


def decide(
    *,
    evidence_state: EvidenceState,
    authority_state: AuthorityState,
    outside_mandate_scope: bool,
    resolvable_by_authorized_source: bool,
) -> tuple[AuthorityVerdict, list[str]]:
    reasons: list[str] = []

    if outside_mandate_scope or authority_state == AuthorityState.DENIED:
        reasons.append("action falls outside the granted mandate scope")
        return AuthorityVerdict.FORBIDDEN, reasons

    if authority_state == AuthorityState.EXPIRED:
        reasons.append("mandate has expired for this action")
        return AuthorityVerdict.FORBIDDEN, reasons

    if authority_state == AuthorityState.NEEDS_CONSENT:
        reasons.append("this specific action requires the person's confirmation")
        return AuthorityVerdict.CONFIRM, reasons

    if evidence_state in (
        EvidenceState.MISSING,
        EvidenceState.CONFLICTING,
        EvidenceState.STALE,
    ):
        if resolvable_by_authorized_source:
            reasons.append(
                f"evidence is {evidence_state.value}, "
                "and an authorized source can still resolve it"
            )
            return AuthorityVerdict.GATHER_EVIDENCE, reasons
        reasons.append(
            f"evidence is {evidence_state.value} "
            "and no authorized source remains to resolve it"
        )
        return AuthorityVerdict.FORBIDDEN, reasons

    if evidence_state == EvidenceState.SUFFICIENT and authority_state == AuthorityState.GRANTED:
        reasons.append("evidence sufficient and authority granted for this action")
        return AuthorityVerdict.ALLOWED, reasons

    reasons.append("no rule matched explicitly — deny by default")
    return AuthorityVerdict.FORBIDDEN, reasons
