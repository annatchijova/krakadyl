#!/usr/bin/env python3
"""Live red-team probes against the real krakadyl API authority boundary.

Induction, not code-reading: each probe states a prediction, drives the
real uvicorn server over HTTP, and reports HOLDS / BROKEN. It boots the
app with two configured operators (investigator-A, who is the seeded
case's mandate principal, and investigator-C, who is not) on an ephemeral
port with a throwaway data directory, and tears everything down.

Probes:
  P1  read with no token                         -> expect 401
  P2  read with an invalid token                 -> expect 401
  P3  valid operator C prepares on A's mandate   -> expect 403
  P4  A's token but body claims principal=C      -> expect 403
  P5  execute the same prepared action twice     -> expect 2nd NOT executed
  P6  read an unknown case                        -> expect 404
  P7  non-participant operator D reads A's case   -> expect 403 (RT-API-01 closed)
  P8  participant C (verifier) reads A's case     -> expect 200 (collaboration kept)
  P9  participant A (principal) reads A's case    -> expect 200

RT-API-01 (see docs/red-team-api-authority-2026-10-31.md) was the read-side
asymmetry: any configured operator could read any case. Reads now authorize
per-case membership, so P7 is refused while P8/P9 still succeed.

Exit code 0 if every HOLDS/BROKEN assertion matched its prediction. Stdlib
only; uses sys.executable.

Run: python tools/redteam_api_probes.py
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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _req(method, url, token=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        return exc.code, payload


def main() -> int:
    tok_a = secrets.token_urlsafe(32)   # mandate principal + owner on case-001
    tok_c = secrets.token_urlsafe(32)   # independent verifier on case-001 (a participant)
    tok_d = secrets.token_urlsafe(32)   # a configured operator with NO relationship to case-001
    hash_a = hashlib.sha256(tok_a.encode()).hexdigest()
    hash_c = hashlib.sha256(tok_c.encode()).hexdigest()
    hash_d = hashlib.sha256(tok_d.encode()).hexdigest()
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.mkdtemp(prefix="krakadyl-redteam-")

    env = dict(os.environ)
    env["KRAKADYL_OPERATOR_TOKENS"] = (
        f"investigator-A={hash_a};investigator-C={hash_c};investigator-D={hash_d}"
    )
    env["KRAKADYL_DATA_DIR"] = tmp
    env["KRAKADYL_ENABLE_DEV_ROUTES"] = "0"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "krakadyl.api.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    failures = []

    def check(name, prediction, observed, ok):
        print(f"[{name}] predict {prediction} | observed {observed} | {'HOLDS' if ok else '*** BROKEN ***'}")
        if not ok:
            failures.append(name)

    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise SystemExit(f"server exited early with {proc.returncode}")
            try:
                if _req("GET", f"{base}/api/cases/case-001", tok_a)[0] == 200:
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
            time.sleep(0.2)
        else:
            raise SystemExit("server never came up")

        print("server up; running probes\n")

        st, _ = _req("GET", f"{base}/api/cases/case-001", None)
        check("P1 no-token-read", "401", st, st == 401)

        st, _ = _req("GET", f"{base}/api/cases/case-001", "not-a-real-token")
        check("P2 bad-token-read", "401", st, st == 401)

        st, _ = _req("POST", f"{base}/api/cases/case-001/actions/prepare", tok_c,
                     {"principal": "investigator-C", "allowed_device": "device-A", "destination": "reviewer-authorized"})
        check("P3 C-prepares-A-mandate", "403", st, st == 403)

        st, _ = _req("POST", f"{base}/api/cases/case-001/actions/prepare", tok_a,
                     {"principal": "investigator-C", "allowed_device": "device-A", "destination": "reviewer-authorized"})
        check("P4 A-token-body-claims-C", "403", st, st == 403)

        st, _ = _req("GET", f"{base}/api/cases/case-999", tok_a)
        check("P6 unknown-case", "404", st, st == 404)

        st, prep = _req("POST", f"{base}/api/cases/case-001/actions/prepare", tok_a,
                        {"principal": "investigator-A", "allowed_device": "device-A", "destination": "reviewer-authorized"})
        pid = prep.get("prepared", {}).get("id")
        _, ex1 = _req("POST", f"{base}/api/cases/case-001/actions/execute", tok_a,
                      {"principal": "investigator-A", "prepared_action_id": pid})
        _, ex2 = _req("POST", f"{base}/api/cases/case-001/actions/execute", tok_a,
                      {"principal": "investigator-A", "prepared_action_id": pid})
        exec1 = ex1.get("receipt", {}).get("executed")
        exec2 = ex2.get("receipt", {}).get("executed")
        check("P5 replay-execute", "2nd NOT executed", f"exec1={exec1} exec2={exec2}",
              exec1 is True and exec2 is not True)

        # RT-API-01, now closed. Reads are authorized per-case: a configured
        # operator with no relationship to the case is refused, while the
        # case's participants (the mandate principal A and the independent
        # verifier C) still read it — so Level 4 collaboration is preserved.
        st, _ = _req("GET", f"{base}/api/cases/case-001", tok_d)
        check("P7 D-reads-A-case (non-participant)", "403", st, st == 403)

        st, _ = _req("GET", f"{base}/api/cases/case-001", tok_c)
        check("P8 C-reads-A-case (participant/verifier)", "200", st, st == 200)

        st, _ = _req("GET", f"{base}/api/cases/case-001", tok_a)
        check("P9 A-reads-A-case (participant/principal)", "200", st, st == 200)

        print("\n=== SUMMARY ===")
        print("  all authority assertions HOLD" if not failures else f"  BROKEN: {failures}")
        return 1 if failures else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
