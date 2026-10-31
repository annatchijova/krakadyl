#!/usr/bin/env python3
"""Live red-team of Level 5 comparable routes (counterfactuals).

Induction against a running uvicorn server. Confirms the Level 5 core promises
and the RT-API-02 fix (see docs/red-team-level5-counterfactuals-2026-10-31.md):

  L5-iso    creating a counterfactual writes NO real case object (no decision,
            receipt, or prepared action); it lives only in the counterfactuals
            table, separate from `objects`.
  L5-stale  a fresh counterfactual is not stale; after the real inputs change
            (mandate revoked), it is flagged stale.
  L5-noexec a counterfactual id is not an executable prepared action.
  RT-API-02 a non-participant operator cannot read real case state through
            POST /counterfactuals (it echoes the case's real outcome); a
            participant can.

Exit 0 if every invariant holds. Stdlib only; uses sys.executable.
Run: python tools/redteam_level5_probes.py
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
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CF_BODY = {
    "question": {"operation": "package_export", "allowed_device": "device-A", "destination": "reviewer-authorized"},
    "deltas": [{"kind": "grant_resource", "value": "case-001/device-B"}],
}


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
    tok_a = secrets.token_urlsafe(32)   # the seed mandate principal -> a case member
    tok_d = secrets.token_urlsafe(32)   # a configured operator with no case relationship
    operators = (f"investigator-A={hashlib.sha256(tok_a.encode()).hexdigest()};"
                 f"investigator-D={hashlib.sha256(tok_d.encode()).hexdigest()}")
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.mkdtemp(prefix="krakadyl-l5-")
    db = Path(tmp) / "krakadyl.db"

    env = dict(os.environ)
    env["KRAKADYL_OPERATOR_TOKENS"] = operators
    env["KRAKADYL_DATA_DIR"] = tmp
    env["KRAKADYL_ENABLE_DEV_ROUTES"] = "1"   # needed to mutate real inputs for the staleness probe
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "krakadyl.api.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    C = f"{base}/api/cases/case-001"

    def object_counts():
        con = sqlite3.connect(str(db))
        try:
            objs = dict(con.execute(
                "SELECT kind, COUNT(*) FROM objects WHERE case_id='case-001' GROUP BY kind").fetchall())
            cf = con.execute("SELECT COUNT(*) FROM counterfactuals WHERE case_id='case-001'").fetchone()[0]
        finally:
            con.close()
        return objs, cf

    results = []

    def check(name, ok, detail=""):
        print(f"[{name}] {'HOLDS' if ok else '*** BROKEN ***'} {detail}")
        results.append(ok)

    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise SystemExit(f"server exited early with {proc.returncode}")
            try:
                if _req("GET", C, tok_a)[0] == 200:
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
            time.sleep(0.2)
        else:
            raise SystemExit("server never came up")
        print("server up\n")

        # RT-API-02: a non-member cannot read real case state via POST.
        dcase, _ = _req("GET", C, tok_d)
        dpost, _ = _req("POST", f"{C}/counterfactuals", tok_d, CF_BODY)
        check("RT-API-02 non-member blocked", dcase == 403 and dpost == 403, f"GET {dcase}, POST {dpost}")

        # L5-iso: a member's counterfactual creates no real object.
        objs_before, cf_before = object_counts()
        st, view = _req("POST", f"{C}/counterfactuals", tok_a, CF_BODY)
        objs_after, cf_after = object_counts()
        check("L5-iso isolation", st == 200 and objs_after == objs_before and cf_after == cf_before + 1,
              f"objects stable={objs_after == objs_before}, cf {cf_before}->{cf_after}")
        check("L5-stale fresh not stale", view.get("stale") is False)

        # L5-stale: after a real input change, the counterfactual is stale.
        rv, _ = _req("POST", f"{base}/api/dev/cases/case-001/revoke-mandate", tok_a, {"reason": "probe"})
        st, views = _req("GET", f"{C}/counterfactuals", tok_a)
        check("L5-stale flagged after inputs change", bool(views) and all(v["stale"] for v in views),
              f"flags={[v['stale'] for v in views]}")

        # L5-noexec: a counterfactual id is not an executable prepared action.
        cf_id = views[0]["counterfactual"]["counterfactual_id"]
        st_x, _ = _req("POST", f"{C}/actions/execute", tok_a,
                       {"principal": "investigator-A", "prepared_action_id": cf_id})
        check("L5-noexec cf id is not executable", st_x != 200, f"execute(cf_id) -> {st_x}")

        print("\n=== VERDICT:",
              "Level 5 invariants HOLD (isolation, staleness, non-executability, membership)"
              if all(results) else "*** A LEVEL 5 INVARIANT BROKEN ***", "===")
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
