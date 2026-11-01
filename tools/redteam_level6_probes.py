#!/usr/bin/env python3
"""Live red-team of Level 6 delegation under adversarial use.

Induction against a running uvicorn server. A senior (investigator-A) delegates
a device-A-only sub-mandate to a junior (investigator-J); the probes confirm the
delegation cannot be stretched past its chain and dies when an ancestor dies,
even mid-flight:

  RT-L6-1  the junior prepares an action outside the slice (device-B, which the
           sub does not hold though the parent does)      -> expect 409
  RT-L6-3  a sub-sub delegated from the sub tries to widen back to device-B
           (transitive closure)                           -> expect 409
  RT-L6-2  the parent is revoked BETWEEN the junior's prepare and execute; the
           execute is refused at the chain re-check        -> expect 409

See docs/red-team-level6-delegation-2026-11-01.md. Exit 0 if every assertion
matches its prediction. Stdlib only; uses sys.executable.
Run: python tools/redteam_level6_probes.py
"""
import hashlib,json,os,secrets,shutil,socket,subprocess,sys,tempfile,time,urllib.error,urllib.request
from pathlib import Path
REPO=Path("/home/labestiadevigia/krakadyl")
def fp():
    s=socket.socket(); s.bind(("127.0.0.1",0)); p=s.getsockname()[1]; s.close(); return p
def req(m,u,t,b=None):
    d=json.dumps(b).encode() if b is not None else None; h={"Authorization":f"Bearer {t}"}
    if d is not None: h["Content-Type"]="application/json"
    r=urllib.request.Request(u,data=d,headers=h,method=m)
    try:
        with urllib.request.urlopen(r,timeout=20) as x: return x.status,json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read().decode())
        except: return e.code,{}
toks={k:secrets.token_urlsafe(32) for k in ("A","J")}
hashes=";".join(f"investigator-{k}={hashlib.sha256(v.encode()).hexdigest()}" for k,v in toks.items())
port=fp(); base=f"http://127.0.0.1:{port}"; tmp=tempfile.mkdtemp(prefix="krk-l6-")
env=dict(os.environ); env["KRAKADYL_OPERATOR_TOKENS"]=hashes; env["KRAKADYL_DATA_DIR"]=tmp; env["KRAKADYL_ENABLE_DEV_ROUTES"]="1"
proc=subprocess.Popen([sys.executable,"-m","uvicorn","krakadyl.api.app:app","--host","127.0.0.1","--port",str(port),"--log-level","warning"],cwd=str(REPO),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
C=f"{base}/api/cases/case-001"
results=[]
def chk(n,pred,obs,ok): print(f"[{n}] predict {pred} | observed {obs} | {'HOLDS' if ok else '*** BROKEN ***'}"); results.append(ok)
try:
    dl=time.monotonic()+30
    while time.monotonic()<dl:
        if proc.poll() is not None: print(proc.stdout.read()); raise SystemExit("died")
        try:
            if req("GET",C,toks["A"])[0]==200: break
        except: pass
        time.sleep(0.2)
    print("server up\n")
    until=req("GET",C,toks["A"])[1]["mandate"]["valid_until"]
    # A delegates device-A-only sub to J
    sub=req("POST",f"{C}/mandates/mandate-001/delegations",toks["A"],{"principal":"investigator-J","resources":["case-001/device-A"],"operations":["package_export"],"destinations":["reviewer-authorized"],"valid_until":until})[1]["mandate"]
    sub_id=sub["id"]
    # RT-L6-1: J prepares device-B under a device-A-only sub -> refused (chain gate denies)
    st,body=req("POST",f"{C}/actions/prepare",toks["J"],{"principal":"investigator-J","allowed_device":"device-B","destination":"reviewer-authorized","sub_mandate_id":sub_id})
    chk("RT-L6-1 junior prepares out-of-slice device-B","409",f"HTTP {st}",st==409)
    # RT-L6-3: sub-sub cannot widen beyond the sub (device-B not in sub) -> 409 at derive
    st,body=req("POST",f"{C}/mandates/{sub_id}/delegations",toks["J"],{"principal":"investigator-J","resources":["case-001/device-B"],"operations":["package_export"],"destinations":["reviewer-authorized"],"valid_until":until})
    chk("RT-L6-3 sub-sub widens beyond sub","409",f"HTTP {st}",st==409)
    # RT-L6-2: revoke parent BETWEEN prepare and execute -> execute refused at linearization
    st,prep=req("POST",f"{C}/actions/prepare",toks["J"],{"principal":"investigator-J","allowed_device":"device-A","destination":"reviewer-authorized","sub_mandate_id":sub_id})
    pid=prep.get("prepared",{}).get("id"); print(f"   J prepared under sub -> {st} (verdict {prep.get('decision',{}).get('verdict')})")
    rv,_=req("POST",f"{base}/api/dev/cases/case-001/revoke-mandate",toks["A"],{"reason":"reassigned mid-flight"}); print(f"   parent revoked mid-flight -> {rv}")
    st,body=req("POST",f"{C}/actions/execute",toks["J"],{"principal":"investigator-J","prepared_action_id":pid,"sub_mandate_id":sub_id})
    chk("RT-L6-2 execute after parent revoked mid-flight","409",f"HTTP {st}: {str(body.get('detail',''))[:60]}",st==409)
    print("\n=== VERDICT:", "Level 6 delegation holds under adversarial use" if all(results) else "*** A LEVEL 6 INVARIANT BROKEN ***","===")
    sys.exit(0 if all(results) else 2)
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except: proc.kill()
    shutil.rmtree(tmp,ignore_errors=True)
