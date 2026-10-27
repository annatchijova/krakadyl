"""Canonical encoding and chained sealing for receipts.

One canonical encoder, used everywhere a receipt gets hashed — divergent
ad-hoc encoders are how one logical receipt ends up with two different
hashes. Keys are recursively sorted; types are tagged so 1, "1", and 1.0
never collide.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

CANONICALIZE_VERSION = "1"


def _tag(value: Any) -> Any:
    if isinstance(value, bool):
        return {"$bool": value}
    if isinstance(value, int):
        return {"$int": value}
    if isinstance(value, float):
        raise TypeError(
            "float reached the canonical encoder — floats are forbidden "
            "in the sealed decision/receipt path"
        )
    if isinstance(value, str):
        return {"$str": value}
    if value is None:
        return {"$null": True}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, dict):
        return {"$obj": {k: _tag(v) for k, v in sorted(value.items())}}
    if isinstance(value, (list, tuple)):
        return {"$list": [_tag(v) for v in value]}
    raise TypeError(f"unsupported type in canonical payload: {type(value)}")


def canonical_bytes(payload: dict) -> bytes:
    tagged = {"$version": CANONICALIZE_VERSION, "$payload": _tag(payload)}
    return json.dumps(tagged, sort_keys=True, separators=(",", ":")).encode("utf-8")


def seal(payload: dict, prev_hash: str | None) -> str:
    body = canonical_bytes(payload)
    h = hashlib.sha256()
    if prev_hash:
        h.update(prev_hash.encode("utf-8"))
    h.update(body)
    return h.hexdigest()
