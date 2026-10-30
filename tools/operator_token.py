#!/usr/bin/env python3
"""Generate operator bearer tokens for a local KRAKADYL deployment. Stdlib only.

Prints each token ONCE (give it to that investigator; it is never
stored) and the KRAKADYL_OPERATOR_TOKENS value to configure, which
holds only SHA-256 hashes.

Usage: python tools/operator_token.py investigator-A investigator-C
"""

import hashlib
import re
import secrets
import sys


def main(identities: list[str]) -> int:
    if not identities:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    entries = []
    for identity in identities:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", identity):
            print(f"invalid identity: {identity!r}", file=sys.stderr)
            return 2
        token = secrets.token_urlsafe(32)
        print(f"{identity}: {token}")
        entries.append(f"{identity}={hashlib.sha256(token.encode()).hexdigest()}")
    print()
    print(f"export KRAKADYL_OPERATOR_TOKENS='{';'.join(entries)}'")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
