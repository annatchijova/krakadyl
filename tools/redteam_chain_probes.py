#!/usr/bin/env python3
"""Live red-team: receipt-chain integrity under REAL concurrent HTTP execution.

The suite's concurrency tests run at the store layer (two store instances,
threads, a barrier) and in-process (the handler called directly). Neither drives
a real uvicorn server, and the fork this probe hunts only appears when many
concurrent HTTP executions race through the real request path. The oracle reads
the persisted receipt rows straight from SQLite and checks the chain shape from
the bytes — it does not trust any traversal the app provides.

Two scenarios, one live server:
  * DISTINCT: N distinct prepared actions executed concurrently, several rounds.
    Each round must add N receipts and the persisted chain must stay a single
    hash-linked line (one root, no two receipts sharing a predecessor = no fork,
    no dangling prev_hash, no duplicate hash).
  * REPLAY: M concurrent executions of ONE prepared action. Exactly one executes
    (the one-shot nonce), the rest are denied, and the chain gains exactly one
    receipt with no dangling link even if a denied append won the lock first.

This is the induction behind RT-CHAIN-01 (head was selected by a handler-side
timestamp, not append order) and RT-CHAIN-02 (a successful receipt replacing a
denied one linked to the row it was about to overwrite). See
docs/red-team-receipt-chain-concurrency-2026-10-31.md.

Exit 0 if the chain invariant holds throughout; non-zero otherwise. Stdlib only.
Run: python tools/redteam_chain_probes.py
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

REPO = Path(__file__).resolve().parent.parent
ROUNDS = 3
N = 8          # distinct concurrent executions per round
M = 6          # concurrent executions of one action (replay race)


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
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.mkdtemp(prefix="krakadyl-chain-")
    db = Path(tmp) / "krakadyl.db"

    env = dict(os.environ)
    env["KRAKADYL_OPERATOR_TOKENS"] = f"investigator-A={token_hash}"
    env["KRAKADYL_DATA_DIR"] = tmp
    env["KRAKADYL_ENABLE_DEV_ROUTES"] = "0"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "krakadyl.api.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    def persisted():
        con = sqlite3.connect(str(db))
        try:
            rows = con.execute(
                "SELECT json FROM objects WHERE case_id='case-001' AND kind='receipt'"
            ).fetchall()
        finally:
            con.close()
        return [json.loads(r[0]) for r in rows]

    def prepare():
        st, b = _req("POST", f"{base}/api/cases/case-001/actions/prepare", token,
                     {"principal": "investigator-A", "allowed_device": "device-A", "destination": "reviewer-authorized"})
        assert st == 200, (st, b)
        return b["prepared"]["id"]

    def burst(pids):
        barrier = Barrier(len(pids))

        def fire(pid):
            barrier.wait(timeout=10)
            return _req("POST", f"{base}/api/cases/case-001/actions/execute", token,
                        {"principal": "investigator-A", "prepared_action_id": pid})
        with ThreadPoolExecutor(max_workers=len(pids)) as pool:
            return list(pool.map(fire, pids))

    def chain_shape(expected_total):
        rs = persisted()
        hashes = [r["hash"] for r in rs]
        counts = Counter((r.get("prev_hash") or "ROOT") for r in rs)
        hashset = set(hashes)
        forks = {k[:10]: v for k, v in counts.items() if v > 1}
        dangling = [p for p in (r.get("prev_hash") for r in rs) if p is not None and p not in hashset]
        ok = (
            len(rs) == expected_total
            and counts.get("ROOT", 0) == 1
            and not forks
            and not dangling
            and len(hashes) == len(hashset)
        )
        return ok, dict(n=len(rs), roots=counts.get("ROOT", 0), fork=forks or False, dangling=dangling,
                        duphash=len(hashes) != len(hashset))

    failures = []
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise SystemExit(f"server exited early with {proc.returncode}")
            try:
                if _req("GET", f"{base}/api/cases/case-001", token)[0] == 200:
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
            time.sleep(0.2)
        else:
            raise SystemExit("server never came up")
        print("server up\n")

        total = 0
        for rnd in range(1, ROUNDS + 1):
            resp = burst([prepare() for _ in range(N)])
            executed = sum(1 for _, b in resp if b.get("receipt", {}).get("executed") is True)
            total += N
            ok, shape = chain_shape(total)
            print(f"round {rnd} distinct N={N}: executed {executed}/{N} | chain {shape} | {'OK' if ok and executed == N else 'FAIL'}")
            if not (ok and executed == N):
                failures.append(f"round{rnd}")

        pid = prepare()
        resp = burst([pid] * M)
        executed = sum(1 for _, b in resp if b.get("receipt", {}).get("executed") is True)
        denied = sum(1 for _, b in resp if b.get("receipt", {}).get("executed") is False)
        total += 1
        ok, shape = chain_shape(total)
        print(f"replay M={M} one action: executed {executed}/{M} (expect 1), denied {denied}/{M} (expect {M-1}) "
              f"| chain {shape} | {'OK' if ok and executed == 1 and denied == M - 1 else 'FAIL'}")
        if not (ok and executed == 1 and denied == M - 1):
            failures.append("replay")

        print("\n=== VERDICT:",
              "single intact receipt chain under live concurrency + replay (HOLDS)"
              if not failures else f"*** CHAIN INVARIANT BROKEN: {failures} ***", "===")
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
