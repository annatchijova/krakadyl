"""Laya adapter — a typed semantic sensor, never a source of authority.

Per `docs/levels.md` invariant 2 ("Laya as a typed semantic sensor that
informs what to check; it never grants authority by itself"): this
module turns unstructured text — the shape a handoff note, a chat
message, or an investigator's free-text comment actually takes — into
typed, bounded signals (`noul` = probability in [0, 1], `score` =
bounded numeric estimate). Those signals inform a HUMAN about what to
verify. Nothing in `krakadyl.core` reads this module's output, and
nothing here is permitted to set `TaskResponsibility.status`,
`EvidenceRequirement.resolved`, or any other fact the policy engine
decides on — a classification is a reason to look, never a reason to
mark something verified.

Laya itself runs locally (no network call, no billing) via a small
ModernBERT-family classifier — see https://github.com/NandhaKishorM/laya.
The import is lazy and the dependency optional: a deployment without
`laya` installed loses this one signal, not the rest of the product
(`honest-degradation`'s "an absent optional component degrades the
feature, never the core").
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol

from pydantic import BaseModel

HANDOFF_QUESTIONS: dict[str, dict[str, Any]] = {
    "claims_independent_verification": {
        "type": "noul",
        "instructions": (
            "Does this note claim that someone OTHER than the person who did the "
            "original work independently checked or verified it? A note that only "
            "says the work was done, with no mention of a separate check, should "
            "score this low."
        ),
    },
    "claims_task_complete": {
        "type": "noul",
        "instructions": "Does this note assert that the described task is finished?",
    },
    "urgency": {
        "type": "score",
        "instructions": "How time-urgent does this note sound?",
        # Found by the first live call: a `score` question takes
        # `criteria` as a LIST of level descriptions, index 0 first —
        # not the `legend` dict shape (that's part of Laya's *output*
        # for a score answer, not a valid input field). Fixed at the
        # source, matching the real validator in laya/agent.py's
        # `_check_question`, not guessed from the README example alone.
        "criteria": [
            "no urgency conveyed",
            "some urgency, but not immediate",
            "immediately urgent, must be acted on now",
        ],
    },
}


class LayaAdapterError(Exception):
    pass


class LayaSignals(BaseModel):
    """Typed output of one `analyze_handoff_note` call. Every field is a
    bounded number with an explicit meaning — never free text, and
    never a verdict. `raw` keeps Laya's full response for a human who
    wants to see the underlying probabilities/confidence, not because
    any code path reads it.
    """

    claims_independent_verification: float
    claims_task_complete: float
    urgency: float
    raw: dict[str, Any]


class RouterLike(Protocol):
    def predict(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]: ...


RouterFactory = Callable[[], RouterLike]


def _default_router_factory() -> RouterLike:
    try:
        from laya import Router  # type: ignore[import-not-found]
    except ImportError as exc:
        raise LayaAdapterError(
            "the 'laya' package is not installed — this signal is unavailable, "
            "the rest of the case is unaffected"
        ) from exc
    return Router()


_router_singleton: Optional[RouterLike] = None


def analyze_handoff_note(
    note_text: str,
    *,
    router_factory: RouterFactory = _default_router_factory,
    reuse_singleton: bool = True,
) -> LayaSignals:
    """Classifies one piece of free text into typed signals. Never
    raises on a low-confidence answer — low confidence is itself
    information for the human reading the signal, not a reason to
    hide it. Raises `LayaAdapterError` only when Laya itself can't run
    (not installed, model load failure) or returns something that
    doesn't match the expected shape — never silently returns a
    fabricated signal.

    `reuse_singleton` keeps one loaded model across calls within a
    process (loading the checkpoint is the expensive part) — set to
    False in tests that inject their own `router_factory` so a fake
    router is never accidentally skipped in favor of a cached real one.
    """
    global _router_singleton

    if reuse_singleton:
        if _router_singleton is None:
            _router_singleton = router_factory()
        router = _router_singleton
    else:
        router = router_factory()

    try:
        result = router.predict({"body": note_text}, HANDOFF_QUESTIONS)
        answers = result["answers"]
        raw_urgency_score = float(answers["urgency"]["score"])
        return LayaSignals(
            claims_independent_verification=float(
                answers["claims_independent_verification"]["noul"]
            ),
            claims_task_complete=float(answers["claims_task_complete"]["noul"]),
            # A `score` answer is the expected value over the level
            # INDICES of `criteria` (0 .. len(criteria)-1), weighted by
            # each level's probability — found by the second live call
            # returning 1.76 with a 3-level criteria list, which is
            # nonsensical as a [0, 1] probability but exactly right as
            # an index expectation (max index 2). Normalized here so
            # LayaSignals keeps a single, honest contract — "every
            # field is a bounded [0, 1] number" — instead of asking
            # every caller (including the frontend's progress bars) to
            # know and divide by the current number of criteria levels.
            urgency=raw_urgency_score / (len(HANDOFF_QUESTIONS["urgency"]["criteria"]) - 1),
            raw=result,
        )
    except LayaAdapterError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise LayaAdapterError(f"Laya response did not match the expected shape: {exc}") from exc
