#!/usr/bin/env python3
"""Live-server smoke check — the one thing TestClient cannot prove.

The pytest suite drives the API through `fastapi.testclient.TestClient`,
which runs the app inside the test process and never binds a socket or
starts uvicorn's own event loop. That is the right tool for the decision
logic, but it cannot catch a defect that only appears when a real uvicorn
server dispatches a sync route onto an AnyIO worker thread — exactly the
class of "the server hangs even though the tests pass" problem this repo
once recorded as a blocker.

This script closes that gap. It boots the real, unmodified
`krakadyl.api.app:app` under uvicorn in a subprocess, on an ephemeral
port, with a throwaway operator token and a throwaway data directory,
then drives the core narrative over HTTP for real:

    GET  /api/cases/case-001            (a sync route -> worker thread)
    POST /api/cases/case-001/actions/prepare
    POST /api/cases/case-001/actions/execute

and asserts a sealed, executed receipt comes back. It tears the server
and the temp directory down whether it passes or fails. Stdlib only, so
it has no dependency the API itself doesn't already pull in; it uses the
same interpreter that runs it (`sys.executable`), so it exercises the
environment it is run in, not some other Python.

Exit code 0 means the live server served the full narrative; any other
exit code prints why. This is deliberately NOT a pytest test: it starts a
real server process and is meant to be run explicitly as a demo-readiness
and environment check, not inside the unit-test run.

Usage: python tools/api_smoke.py
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

CASE_ID = "case-001"
PRINCIPAL = "investigator-A"
ALLOWED_DEVICE = "device-A"
DESTINATION = "reviewer-authorized"
STARTUP_TIMEOUT_S = 30.0
REQUEST_TIMEOUT_S = 15.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _request(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return exc.code, {"error": detail}


def _wait_until_up(base: str, token: str, proc: subprocess.Popen) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    last_err = "no attempt made"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"FAIL: server process exited early with code {proc.returncode}")
        try:
            status, _ = _request("GET", f"{base}/api/cases/{CASE_ID}", token)
            if status == 200:
                return
            last_err = f"HTTP {status}"
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_err = str(exc)
        time.sleep(0.25)
    raise SystemExit(f"FAIL: server did not answer within {STARTUP_TIMEOUT_S:.0f}s (last: {last_err})")


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    port = _free_port()
    base = f"http://127.0.0.1:{port}"

    tmp = tempfile.mkdtemp(prefix="krakadyl-api-smoke-")
    env = dict(os.environ)
    env["KRAKADYL_OPERATOR_TOKENS"] = f"{PRINCIPAL}={token_hash}"
    env["KRAKADYL_DATA_DIR"] = tmp
    # A smoke check never needs the tampering/revocation dev routes.
    env["KRAKADYL_ENABLE_DEV_ROUTES"] = "0"

    print(f"Booting real uvicorn server on {base} (data dir {tmp}) ...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "krakadyl.api.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(repo_root), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait_until_up(base, token, proc)
        print("Server is up; driving the core narrative over HTTP.")

        t0 = time.monotonic()
        status, overview = _request("GET", f"{base}/api/cases/{CASE_ID}", token)
        if status != 200:
            raise SystemExit(f"FAIL: case overview returned HTTP {status}: {overview}")
        print(f"  GET  case overview           -> 200 in {(time.monotonic() - t0) * 1000:.0f} ms")

        t0 = time.monotonic()
        status, prep = _request(
            "POST", f"{base}/api/cases/{CASE_ID}/actions/prepare", token,
            {"principal": PRINCIPAL, "allowed_device": ALLOWED_DEVICE, "destination": DESTINATION},
        )
        if status != 200:
            raise SystemExit(f"FAIL: prepare returned HTTP {status}: {prep}")
        verdict = prep.get("decision", {}).get("verdict")
        prepared_id = prep.get("prepared", {}).get("id")
        if verdict != "allowed" or not prepared_id:
            raise SystemExit(f"FAIL: prepare did not produce an allowed prepared action: {prep}")
        print(f"  POST prepare                 -> 200 in {(time.monotonic() - t0) * 1000:.0f} ms (verdict {verdict})")

        t0 = time.monotonic()
        status, ex = _request(
            "POST", f"{base}/api/cases/{CASE_ID}/actions/execute", token,
            {"principal": PRINCIPAL, "prepared_action_id": prepared_id},
        )
        if status != 200:
            raise SystemExit(f"FAIL: execute returned HTTP {status}: {ex}")
        receipt = ex.get("receipt", {})
        if not receipt.get("executed") or not receipt.get("hash"):
            raise SystemExit(f"FAIL: execute did not produce a sealed, executed receipt: {ex}")
        print(f"  POST execute                 -> 200 in {(time.monotonic() - t0) * 1000:.0f} ms")
        print(f"       sealed receipt hash     -> {receipt['hash']}")

        print("\nPASS: the live uvicorn server served GET + prepare + execute end to end.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
