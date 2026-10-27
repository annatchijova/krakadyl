#!/usr/bin/env python3
"""Independent receipt-chain verifier. Stdlib only, on purpose.

This file must never import anything from krakadyl.core — if it did,
a bug in the canonical encoder could pass its own verification. It
reimplements the canonicalization rules by reading this file's own
logic, not by calling the project's code, so the two can disagree and
that disagreement is exactly what this tool exists to catch.

Usage: python tools/verify_receipt.py chain.json
Input: a JSON array of {"payload": {...}, "prev_hash": str|null, "hash": str}
"""

import hashlib
import json
import sys


def tag(value):
    if isinstance(value, bool):
        return {"$bool": value}
    if isinstance(value, int):
        return {"$int": value}
    if isinstance(value, float):
        raise TypeError("float in payload — sealed path must not contain floats")
    if isinstance(value, str):
        return {"$str": value}
    if value is None:
        return {"$null": True}
    if isinstance(value, dict):
        return {"$obj": {k: tag(v) for k, v in sorted(value.items())}}
    if isinstance(value, list):
        return {"$list": [tag(v) for v in value]}
    raise TypeError(f"unsupported type: {type(value)}")


def canonical_bytes(payload):
    tagged = {"$version": "1", "$payload": tag(payload)}
    return json.dumps(tagged, sort_keys=True, separators=(",", ":")).encode("utf-8")


def seal(payload, prev_hash):
    h = hashlib.sha256()
    if prev_hash:
        h.update(prev_hash.encode("utf-8"))
    h.update(canonical_bytes(payload))
    return h.hexdigest()


def main(path: str) -> int:
    with open(path) as f:
        chain = json.load(f)

    prev = None
    for i, entry in enumerate(chain):
        expected = seal(entry["payload"], prev)
        if expected != entry["hash"]:
            print(f"BROKEN at entry {i}: expected {expected}, got {entry['hash']}")
            return 1
        if entry.get("prev_hash") != prev:
            print(f"BROKEN at entry {i}: prev_hash link does not match")
            return 1
        prev = entry["hash"]

    print(f"OK — {len(chain)} entries, chain intact, final hash {prev}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: verify_receipt.py <chain.json>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
