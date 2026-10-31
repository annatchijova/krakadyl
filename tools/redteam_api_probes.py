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
  P7  valid operator C reads A's case overview   -> OBSERVE (read-authorization
                                                    granularity; see
                                                    docs/red-team-api-authority-2026-10-31.md)

Exit code 0 if every HOLDS/BROKEN assertion matched its prediction; P7 is
observational and never fails the run. Stdlib only; uses sys.executable.

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
    tok_a = secrets.token_urlsafe(32)
    tok_c = secrets.token_urlsafe(32)
    hash_a = hashlib.sha256(tok_a.encode()).hexdigest()
    hash_c = hashlib.sha256(tok_c.encode()).hexdigest()
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.mkdtemp(prefix="krakadyl-redteam-")

    env = dict(os.environ)
    env["KRAKADYL_OPERATOR_TOKENS"] = f"investigator-A={hash_a};investigator-C={hash_c}"
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

        # P7 is observational: it records read-authorization granularity, it
        # does not assert a pass/fail. 200 means any configured operator can
        # read any case overview; writes stay per-mandate (P3).
        st, _ = _req("GET", f"{base}/api/cases/case-001", tok_c)
        print(f"[P7 C-reads-A-case] OBSERVE | observed {st} "
              f"({'any operator reads any case' if st == 200 else 'read is case-scoped'})")

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
