import { useCallback, useState } from "react";
import {
  api,
  type ActivityEvent,
  type CaseOverview,
  type Decision,
  type ExecuteResponse,
  type PreparedAction,
  type RecoverResponse,
} from "./api";
import { CaseSidebar } from "./components/CaseSidebar";
import { EvidencePanel } from "./components/EvidencePanel";
import { NextMovePanel } from "./components/NextMovePanel";
import { ActivityFeed } from "./components/ActivityFeed";
import { DevPanel } from "./components/DevPanel";
import { LayaNotePanel } from "./components/LayaNotePanel";
import { AcquisitionPanel } from "./components/AcquisitionPanel";
import { TeamPanel } from "./components/TeamPanel";
import { WhatIfPanel } from "./components/WhatIfPanel";
import { DelegationPanel } from "./components/DelegationPanel";
import { ResumePanel } from "./components/ResumePanel";
import { Logo } from "./components/Logo";
import { SituationStrip } from "./components/SituationStrip";

const CASE_ID = "case-001";

function App() {
  const [overview, setOverview] = useState<CaseOverview | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [prepared, setPrepared] = useState<PreparedAction | null>(null);
  const [recoverInfo, setRecoverInfo] = useState<RecoverResponse | null>(null);
  const [executeResult, setExecuteResult] = useState<ExecuteResponse | null>(null);
  const [museReasoning, setMuseReasoning] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Operator token for Level 3 actions — React state only, never persisted.
  const [operatorToken, setOperatorToken] = useState("");
  const [pendingOperatorToken, setPendingOperatorToken] = useState("");

  const refresh = useCallback(async () => {
    const [o, a] = await Promise.all([api.getCase(CASE_ID), api.getActivity(CASE_ID)]);
    setOverview(o);
    setActivity(a);
  }, []);

  async function authenticate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = pendingOperatorToken.trim();
    if (!token) return;
    setOperatorToken(token);
    api.setOperatorToken(token);
    setOverview(null);
    setError(null);
    try {
      await refresh();
    } catch (e) {
      api.setOperatorToken("");
      setOperatorToken("");
      setError(String(e));
    }
  }

  async function guarded(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const handlePrepare = () =>
    guarded(async () => {
      const res = await api.prepare(CASE_ID);
      setDecision(res.decision);
      setPrepared(res.prepared);
      setRecoverInfo(null);
      setExecuteResult(null);
      setMuseReasoning(null);
    });

  const handleAskMuse = () =>
    guarded(async () => {
      const res = await api.proposeWithMuse(CASE_ID);
      setDecision(res.decision);
      setPrepared(res.prepared);
      setRecoverInfo(null);
      setExecuteResult(null);
      setMuseReasoning(res.muse_reasoning);
    });

  const handleExecute = (preparedActionId: string) =>
    guarded(async () => {
      const res = await api.execute(CASE_ID, preparedActionId);
      setExecuteResult(res);
    });

  const handleRecover = () =>
    guarded(async () => {
      const res = await api.recover(CASE_ID);
      setRecoverInfo(res);
      setDecision(res.decision);
      setPrepared(res.prepared);
      setExecuteResult(null);
    });

  const handleTamper = () => guarded(() => api.devTamper(CASE_ID, "obs-a1").then(() => undefined));
  const handleRevokeMandate = () => guarded(() => api.devRevokeMandate(CASE_ID).then(() => undefined));
  const handleUnresolveHypothesis = () =>
    guarded(() => api.devUnresolveHypothesisRequirement(CASE_ID).then(() => undefined));
  const handleReset = () =>
    guarded(async () => {
      await api.devReset(CASE_ID, operatorToken);
      setDecision(null);
      setPrepared(null);
      setRecoverInfo(null);
      setExecuteResult(null);
      setMuseReasoning(null);
    });

  return (
    <>
      <header className="app-header">
        <Logo />
        <strong style={{ letterSpacing: "0.02em" }}>KRAKADYL</strong>
        <span className="tagline">From evidence to your next move.</span>
      </header>

      {error && <div className="error-banner">{error}</div>}

      {!operatorToken ? (
        <main style={{ maxWidth: 560, margin: "3rem auto", padding: "0 1.4rem" }}>
          <section className="panel">
            <h2>Operator authentication</h2>
            <p className="reason-text">
              Enter the bearer token configured for this deployment. It stays in this tab's memory and is never persisted.
            </p>
            <form onSubmit={authenticate}>
              <input
                type="password"
                autoFocus
                autoComplete="off"
                placeholder="Operator token"
                value={pendingOperatorToken}
                onChange={(e) => setPendingOperatorToken(e.target.value)}
                style={{ width: "100%", boxSizing: "border-box", padding: "0.55rem" }}
              />
              <button className="button-primary" type="submit" style={{ marginTop: "0.6rem" }}>
                Authenticate
              </button>
            </form>
          </section>
        </main>
      ) : overview ? (
        <div className="workspace-shell">
          <div className="workspace-intro">
            <div>
              <p className="workspace-eyebrow">INVESTIGATION WORKSPACE / {CASE_ID}</p>
              <h1>From evidence to your next move.</h1>
              <p>Trace the case, preserve what can still be recovered, and keep authority explicit.</p>
            </div>
            <nav className="workspace-nav" aria-label="Case sections">
              <a href="#evidence">Evidence</a>
              <a href="#acquisition">Acquisition</a>
              <a href="#handoff">Handoff</a>
              <a href="#delegation">Delegation</a>
              <a href="#tools">Tools</a>
            </nav>
          </div>
          <div className="workspace">
          <aside className="workspace-case" aria-label="Case context">
            <CaseSidebar overview={overview} />
          </aside>
          <main className="workspace-main">
            <SituationStrip caseId={CASE_ID} caseVersion={activity.length} overview={overview} />
            <div id="evidence"><EvidencePanel evidence={overview.evidence} /></div>
            <div className="section-gap" id="acquisition">
              <AcquisitionPanel
                caseId={CASE_ID}
                caseVersion={activity.length}
                onChanged={refresh}
                token={operatorToken}
              />
            </div>
            <div className="section-gap" id="handoff">
              <TeamPanel
                caseId={CASE_ID}
                caseVersion={activity.length}
                token={operatorToken}
                evidence={overview.evidence}
                onChanged={refresh}
              />
            </div>
            <div className="section-gap" id="delegation">
              <DelegationPanel
                caseId={CASE_ID}
                caseVersion={activity.length}
                token={operatorToken}
                rootMandate={overview.mandate}
                onChanged={refresh}
              />
            </div>
            <section className="workspace-tools" id="tools" aria-label="Additional case tools">
              <div className="tools-heading">
                <div>
                  <h2>Additional tools</h2>
                  <p>Open the workspace you need without losing the case overview.</p>
                </div>
                <span className="tools-count">3 modules</span>
              </div>
              <details className="tool-disclosure">
                <summary><span><strong>What if…</strong><small>Compare assumptions against the real case. Hypothetical only.</small></span></summary>
                <WhatIfPanel caseId={CASE_ID} caseVersion={activity.length} token={operatorToken} />
              </details>
              <details className="tool-disclosure">
                <summary><span><strong>Laya handoff note</strong><small>Analyze typed signals, never certify a claim.</small></span></summary>
                <LayaNotePanel busy={busy} onAnalyze={(noteText) => api.analyzeNote(CASE_ID, noteText)} />
              </details>
              <details className="tool-disclosure tool-disclosure-dev">
                <summary><span><strong>Simulation · dev only</strong><small>Mutates demo state; not a real investigative action.</small></span></summary>
                <DevPanel
                  busy={busy}
                  onTamper={handleTamper}
                  onRevokeMandate={handleRevokeMandate}
                  onUnresolveHypothesis={handleUnresolveHypothesis}
                  onReset={handleReset}
                />
              </details>
            </section>
          </main>
          <aside className="workspace-rail" aria-label="Next action and case activity">
            <NextMovePanel
              decision={decision}
              prepared={prepared}
              recoverInfo={recoverInfo}
              executeResult={executeResult}
              museReasoning={museReasoning}
              busy={busy}
              onPrepare={handlePrepare}
              onAskMuse={handleAskMuse}
              onExecute={handleExecute}
              onRecover={handleRecover}
            />
            <ResumePanel caseId={CASE_ID} caseVersion={activity.length} />

            <ActivityFeed events={activity} />
          </aside>
          </div>
        </div>
      ) : (
        <p style={{ padding: "1.4rem" }}>Loading case…</p>
      )}
    </>
  );
}

export default App;
