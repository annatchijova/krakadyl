"""Tests for the Laya adapter's typed-mapping boundary. No test here
loads a real model: `router_factory` is injected, same pattern as the
Muse adapter's `transport` injection — the validation/mapping logic is
what's worth testing without GPU time or a checkpoint download.
"""

import sys

import pytest

from krakadyl.adapters.laya import (
    HANDOFF_QUESTIONS,
    LayaAdapterError,
    LayaSignals,
    analyze_handoff_note,
)


class _FakeRouter:
    def __init__(self, response):
        self._response = response

    def predict(self, state, questions):
        assert "body" in state
        assert "claims_independent_verification" in questions
        return self._response


def _valid_response():
    return {
        "answers": {
            "claims_independent_verification": {"type": "noul", "noul": 0.12},
            "claims_task_complete": {"type": "noul", "noul": 0.91},
            # Raw score is an expected value over criteria-list indices
            # (3 levels -> domain [0, 2]), not already a [0, 1]
            # probability — 1.2 here normalizes to 0.6, the value the
            # test below asserts.
            "urgency": {"type": "score", "score": 1.2},
        },
        "routing": {"model": "laya"},
    }


def test_valid_response_maps_into_typed_signals():
    signals = analyze_handoff_note(
        "Device A is done, haven't had anyone else look at it yet.",
        router_factory=lambda: _FakeRouter(_valid_response()),
        reuse_singleton=False,
    )
    assert isinstance(signals, LayaSignals)
    assert signals.claims_independent_verification == pytest.approx(0.12)
    assert signals.claims_task_complete == pytest.approx(0.91)
    assert signals.urgency == pytest.approx(0.6)
    assert signals.raw["routing"]["model"] == "laya"


def test_score_question_uses_criteria_not_legend():
    """Found by the first real call against live Laya: a `score`
    question's real validator (laya/agent.py::_check_question) requires
    `criteria` as a list of level descriptions — a `legend` dict (the
    shape of a score *answer*, not a question) is rejected outright.
    Locks the fix in so this doesn't regress back to the wrong shape.
    """
    urgency = HANDOFF_QUESTIONS["urgency"]
    assert isinstance(urgency["criteria"], list)
    # >= 2, not just >= 1: analyze_handoff_note() divides by
    # (len(criteria) - 1) to normalize the raw score into [0, 1] — a
    # single-level list would divide by zero.
    assert len(urgency["criteria"]) >= 2
    assert "legend" not in urgency


def test_malformed_response_is_rejected_not_coerced():
    broken = {"answers": {"claims_task_complete": {"noul": 0.5}}}  # missing keys
    with pytest.raises(LayaAdapterError):
        analyze_handoff_note(
            "note",
            router_factory=lambda: _FakeRouter(broken),
            reuse_singleton=False,
        )


def test_missing_package_raises_a_clear_adapter_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "laya", None)  # forces `from laya import Router` to fail
    from krakadyl.adapters import laya as laya_adapter

    with pytest.raises(LayaAdapterError, match="not installed"):
        analyze_handoff_note(
            "note",
            router_factory=laya_adapter._default_router_factory,
            reuse_singleton=False,
        )


def test_singleton_reuse_calls_the_factory_only_once(monkeypatch):
    from krakadyl.adapters import laya as laya_adapter

    monkeypatch.setattr(laya_adapter, "_router_singleton", None)
    call_count = {"n": 0}

    def factory():
        call_count["n"] += 1
        return _FakeRouter(_valid_response())

    analyze_handoff_note("a", router_factory=factory, reuse_singleton=True)
    analyze_handoff_note("b", router_factory=factory, reuse_singleton=True)
    assert call_count["n"] == 1
    monkeypatch.setattr(laya_adapter, "_router_singleton", None)
