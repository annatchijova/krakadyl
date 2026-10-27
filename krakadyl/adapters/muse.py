"""Muse Spark adapter — the model proposes, it never decides.

This is invariant 1 from `docs/levels.md`, applied to the one new input
source this module introduces: everything `propose_action()` returns is
an untrusted candidate, validated against a strict schema before anything
downstream looks at it, and it has no path to becoming an instruction by
itself. The candidate still goes through `check_mandate`/`check_evidence`/
`decide()` exactly like the hand-built `ProposedAction` in
`demo/run_case_001.py` — this module's only job is turning a compressed,
read-only case summary into that typed candidate. `reasoning` is
display-only; nothing in `krakadyl.core` ever reads it.

Standard mode (`muse-spark-1.3`) is the only default on purpose — per the
project's own API-budget note, Contributor mode trades discounted pricing
for Meta's right to train on the content sent, which is never an
acceptable default for anything touching case evidence, even synthetic
evidence. A caller can still pass a different `model` explicitly, but it
is never chosen here.

No third-party HTTP/SDK dependency: the Meta Model API's chat-completions
endpoint is a single JSON POST, and `transport` is injected specifically
so tests never need network access or a mocking library to exercise the
validation logic, which is the part actually worth testing here.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Callable, Optional

from pydantic import BaseModel, ValidationError

API_BASE_URL = "https://api.meta.ai/v1"
MUSE_SPARK_STANDARD = "muse-spark-1.3"


class MuseAdapterError(Exception):
    pass


class ProposedActionCandidate(BaseModel):
    """Untrusted model output. Every field is a plain string — none of
    them is checked against the real mandate or evidence state here;
    `prepare_evidence_package` still does that, unchanged, exactly as it
    does for a hand-built `ProposedAction`.
    """

    operation: str
    allowed_device: str
    destination: str
    reasoning: str


_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "description": "The domain operation this step performs, e.g. 'package_export'.",
        },
        "allowed_device": {
            "type": "string",
            "description": "The single device or source this step is scoped to.",
        },
        "destination": {
            "type": "string",
            "description": "Who or what receives the result.",
        },
        "reasoning": {
            "type": "string",
            "description": "Why this step, in plain language, for a human to read — never a source of authority.",
        },
    },
    "required": ["operation", "allowed_device", "destination", "reasoning"],
    "additionalProperties": False,
}

Transport = Callable[[dict, str], dict]


def _default_transport(payload: dict, api_key: str) -> dict:
    request = urllib.request.Request(
        f"{API_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise MuseAdapterError(f"Muse API returned {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise MuseAdapterError(f"Muse API request failed: {exc.reason}") from exc


def propose_action(
    *,
    mission_summary: str,
    mandate_summary: str,
    case_summary: str,
    api_key: Optional[str] = None,
    model: str = MUSE_SPARK_STANDARD,
    transport: Transport = _default_transport,
) -> ProposedActionCandidate:
    """Calls Muse Spark with a compressed, read-only case summary and
    returns a validated `ProposedActionCandidate`. Raises
    `MuseAdapterError` on a missing key, a transport failure, or a
    response that doesn't match the schema — never coerces a bad
    response into something that looks valid.
    """
    key = api_key or os.environ.get("META_API_KEY")
    if not key:
        raise MuseAdapterError("META_API_KEY not set — refusing to call the Muse API without credentials")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You propose the next investigative action for a forensic "
                    "case. You have no authority to execute anything — a "
                    "separate, deterministic system checks your proposal "
                    "against the real mandate and evidence state before "
                    "anything happens, and will refuse it if it is outside "
                    "scope or the evidence isn't independently verified. "
                    "Propose the single most useful next step given the case "
                    "summary below."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Mission:\n{mission_summary}\n\n"
                    f"Mandate (informational only — not authoritative):\n{mandate_summary}\n\n"
                    f"Case state:\n{case_summary}"
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "ProposedActionCandidate", "schema": _CANDIDATE_SCHEMA},
        },
    }

    raw = transport(payload, key)
    try:
        content = raw["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return ProposedActionCandidate.model_validate(parsed)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
        raise MuseAdapterError(f"Muse response did not match the expected schema: {exc}") from exc
