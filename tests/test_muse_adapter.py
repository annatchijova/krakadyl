"""Tests for the Muse adapter's validation boundary — the only part of
this module worth testing without a real network call. No test here
ever calls the real API: `transport` is a fake, so the schema/rejection
behavior is verified without network access or a mocking library.
"""

import json

import pytest

from krakadyl.adapters.muse import (
    MuseAdapterError,
    ProposedActionCandidate,
    propose_action,
)


def _transport_returning(content) -> callable:
    def transport(payload: dict, api_key: str) -> dict:
        return {"choices": [{"message": {"content": content}}]}

    return transport


def test_valid_response_parses_into_a_typed_candidate():
    content = json.dumps(
        {
            "operation": "package_export",
            "allowed_device": "device-A",
            "destination": "reviewer-authorized",
            "reasoning": "Device A's evidence is independently verified; the mandate covers it.",
        }
    )
    candidate = propose_action(
        mission_summary="Prepare the package for the authorized reviewer.",
        mandate_summary="device-A, package_export, reviewer-authorized",
        case_summary="obs-a1, obs-a2 verified; obs-b1 excluded.",
        api_key="test-key",
        transport=_transport_returning(content),
    )
    assert isinstance(candidate, ProposedActionCandidate)
    assert candidate.operation == "package_export"
    assert candidate.allowed_device == "device-A"
    assert candidate.destination == "reviewer-authorized"


def test_missing_required_field_is_rejected_not_coerced():
    content = json.dumps({"operation": "package_export", "allowed_device": "device-A"})
    with pytest.raises(MuseAdapterError):
        propose_action(
            mission_summary="m",
            mandate_summary="m",
            case_summary="c",
            api_key="test-key",
            transport=_transport_returning(content),
        )


def test_malformed_json_is_rejected():
    with pytest.raises(MuseAdapterError):
        propose_action(
            mission_summary="m",
            mandate_summary="m",
            case_summary="c",
            api_key="test-key",
            transport=_transport_returning("not json"),
        )


def test_missing_choices_is_rejected():
    def transport(payload: dict, api_key: str) -> dict:
        return {}

    with pytest.raises(MuseAdapterError):
        propose_action(
            mission_summary="m",
            mandate_summary="m",
            case_summary="c",
            api_key="test-key",
            transport=transport,
        )


def test_refuses_to_call_without_an_api_key(monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)

    def transport(payload: dict, api_key: str) -> dict:
        raise AssertionError("transport must never be called without a key")

    with pytest.raises(MuseAdapterError, match="META_API_KEY"):
        propose_action(
            mission_summary="m",
            mandate_summary="m",
            case_summary="c",
            api_key=None,
            transport=transport,
        )


def test_standard_mode_is_the_default_model():
    content = json.dumps(
        {
            "operation": "package_export",
            "allowed_device": "device-A",
            "destination": "reviewer-authorized",
            "reasoning": "x",
        }
    )
    seen_payload = {}

    def transport(payload: dict, api_key: str) -> dict:
        seen_payload.update(payload)
        return {"choices": [{"message": {"content": content}}]}

    propose_action(
        mission_summary="m",
        mandate_summary="m",
        case_summary="c",
        api_key="test-key",
        transport=transport,
    )
    assert seen_payload["model"] == "muse-spark-1.3"
    assert not seen_payload["model"].endswith("-contributor")
