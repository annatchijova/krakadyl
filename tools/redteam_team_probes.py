#!/usr/bin/env python3
"""Live red-team of the Level 4 team-coordination authority invariants.

Induction against a running uvicorn server, not code-reading. Boots the real
app with three operators (A, C, D) and exercises the two loud Level 4 promises
over HTTP:

  H1  self-verification: the claimant verifies its own completion claim
                                                         -> expect 409 refused
  H1b independent verification: a non-claimant verifies  -> expect 200 (VERIFIED_DONE)
  H2  a party to a conflict resolves it                  -> expect 409 refused
  H2b a non-party resolves the conflict                  -> expect 200 resolved

These confirm that "verification must come from someone other than the claimant"
and "a conflict is resolved by someone who is not a party to it" hold on the real
request path, under the atomic team-record transaction. See
docs/red-team-level4-team-invariants-2026-10-31.md.

Exit 0 if every assertion matches its prediction. Stdlib only; uses sys.executable.
Run: python tools/redteam_team_probes.py
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REQ = "req-device-a-clock"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _req(method, url, token, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {}


def main() -> int:
    toks = {k: secrets.token_urlsafe(32) for k in ("A", "C", "D")}
    hashes = ";".join(f"investigator-{k}={hashlib.sha256(v.encode()).hexdigest()}" for k, v in toks.items())
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.mkdtemp(prefix="krakadyl-team-")

    env = dict(os.environ)
    env["KRAKADYL_OPERATOR_TOKENS"] = hashes
    env["KRAKADYL_DATA_DIR"] = tmp
    env["KRAKADYL_ENABLE_DEV_ROUTES"] = "0"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "krakadyl.api.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    def team():
        return _req("GET", f"{base}/api/cases/case-001/team", toks["A"])[1]

    def req_view(ov):
        return next(v for v in ov["requirements"] if v["requirement"]["id"] == REQ)

    def post(actor, kind, **extra):
        body = {"kind": kind, "statement": f"{kind} by {actor}",
                "expected_requirement_revision": req_view(team())["requirement_revision"]}
        body.update(extra)
        return _req("POST", f"{base}/api/cases/case-001/requirements/{REQ}/team-records", toks[actor], body)

    results = []

    def check(name, prediction, status, ok):
        print(f"[{name}] predict {prediction} | observed HTTP {status} | {'HOLDS' if ok else '*** BROKEN ***'}")
        results.append(ok)

    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise SystemExit(f"server exited early with {proc.returncode}")
            try:
                if _req("GET", f"{base}/api/cases/case-001", toks["A"])[0] == 200:
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
            time.sleep(0.2)
        else:
            raise SystemExit("server never came up")
        print("server up\n")

        status, _ = post("A", "reported_done")
        print(f"setup: A reported_done -> {status}")
        claim_id = next(r["record_id"] for r in team()["records"]
                        if r["kind"] == "reported_done" and r["actor"] == "investigator-A")

        status, _ = post("A", "verified", refers_to=[claim_id], verification_method="self")
        check("H1 self-verify", 409, status, status == 409)

        status, _ = post("C", "verified", refers_to=[claim_id], verification_method="peer")
        check("H1b cross-verify", 200, status, status == 200)
        final = req_view(team())["requirement"]["responsibility"]["status"]
        print(f"   requirement status now: {final} (expect verified_done)")
        results.append(final == "verified_done")

        status, _ = post("C", "disputed", refers_to=[claim_id])
        print(f"setup: C disputed -> {status}")
        conflicts = req_view(team())["open_conflicts"]
        print(f"   open conflicts: {[(c['kind'], c['parties']) for c in conflicts]}")
        if not conflicts:
            print("   no conflict created; cannot test resolution")
            results.append(False)
        else:
            c0 = conflicts[0]
            rids, cid, parties = list(c0["record_ids"]), c0["conflict_id"], c0["parties"]
            status, _ = post("C", "resolution", refers_to=rids, resolves_conflict_id=cid, decision="keep_current_state")
            check("H2 party-self-resolve", 409, status, status == 409)
            if "investigator-D" not in parties:
                status, _ = post("D", "resolution", refers_to=rids, resolves_conflict_id=cid, decision="keep_current_state")
                check("H2b nonparty-resolve", 200, status, status == 200)
            else:
                print("   D is a party; skipping positive control")

        print("\n=== VERDICT:",
              "all Level 4 team invariants HOLD" if all(results) else "*** A TEAM INVARIANT BROKEN ***", "===")
        return 1 if not all(results) else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
