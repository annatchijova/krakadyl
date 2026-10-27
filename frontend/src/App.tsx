import { useCallback, useEffect, useState } from "react";
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
import { Logo } from "./components/Logo";

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

  const refresh = useCallback(async () => {
    const [o, a] = await Promise.all([api.getCase(CASE_ID), api.getActivity(CASE_ID)]);
    setOverview(o);
    setActivity(a);
  }, []);

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, [refresh]);

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
      await api.devReset(CASE_ID);
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

      {overview ? (
        <div className="workspace">
          <CaseSidebar overview={overview} />
          <div>
            <EvidencePanel evidence={overview.evidence} />
            <div className="section-gap">
              <DevPanel
                busy={busy}
                onTamper={handleTamper}
                onRevokeMandate={handleRevokeMandate}
                onUnresolveHypothesis={handleUnresolveHypothesis}
                onReset={handleReset}
              />
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
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
            <ActivityFeed events={activity} />
          </div>
        </div>
      ) : (
        <p style={{ padding: "1.4rem" }}>Loading case…</p>
      )}
    </>
  );
}

export default App;
