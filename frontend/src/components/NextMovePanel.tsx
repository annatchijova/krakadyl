import type { Decision, ExecuteResponse, PreparedAction, RecoverResponse } from "../api";

function verdictBadge(verdict: Decision["verdict"]) {
  const kind = verdict === "allowed" ? "ok" : verdict === "forbidden" ? "error" : "warn";
  return <span className={`badge ${kind}`}>{verdict}</span>;
}

export function NextMovePanel({
  decision,
  prepared,
  recoverInfo,
  executeResult,
  museReasoning,
  busy,
  onPrepare,
  onAskMuse,
  onExecute,
  onRecover,
}: {
  decision: Decision | null;
  prepared: PreparedAction | null;
  recoverInfo: RecoverResponse | null;
  executeResult: ExecuteResponse | null;
  museReasoning: string | null;
  busy: boolean;
  onPrepare: () => void;
  onAskMuse: () => void;
  onExecute: (preparedActionId: string) => void;
  onRecover: () => void;
}) {
  const canExecute = prepared !== null && executeResult === null;
  const executionFailed = executeResult !== null && !executeResult.receipt.executed;
  const isRecoveryReview = recoverInfo?.prepared != null && executeResult === null;

  return (
    <section className="panel">
      <h2>Next move</h2>

      <div className="action-row">
        <button className="button-primary" onClick={onPrepare} disabled={busy}>
          Prepare package_export
        </button>
        <button className="button-secondary" onClick={onAskMuse} disabled={busy} title="Real Muse Spark call — costs a few cents">
          Ask Muse
        </button>
        {canExecute && (
          <button className="button-secondary" onClick={() => onExecute(prepared!.id)} disabled={busy}>
            {isRecoveryReview ? "Execute this recovery" : "Execute"}
          </button>
        )}
      </div>

      {museReasoning && (
        <div className="recovery-card" style={{ borderColor: "var(--signal)", background: "rgba(214,255,127,0.06)" }}>
          <h3 style={{ color: "var(--signal)" }}>Muse says (not authoritative)</h3>
          <p style={{ margin: 0, fontSize: "0.85rem" }}>{museReasoning}</p>
          <p className="reason-text">
            Still checked against the real mandate and evidence below — this is a proposal, not a decision.
          </p>
        </div>
      )}

      {decision && (
        <div className="section-gap">
          {verdictBadge(decision.verdict)}
          <ul style={{ margin: "0.5rem 0 0 1.1rem", padding: 0, fontSize: "0.85rem" }}>
            {decision.reasons.map((r, i) => (
              <li key={i} className="reason-text">
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {prepared && (
        <div className="section-gap mono" style={{ fontSize: "0.78rem" }}>
          <div>resources: {prepared.resources_touched.join(", ") || "(none)"}</div>
          <div>destination: {prepared.destination}</div>
          <div>expires: {new Date(prepared.expires_at).toLocaleTimeString()}</div>
        </div>
      )}

      {isRecoveryReview && recoverInfo && (
        <div className="recovery-card">
          <h3>Recovery proposal — review before executing</h3>
          <p style={{ margin: "0 0 0.4rem 0", fontSize: "0.85rem" }}>
            Excludes exactly: <strong>{recoverInfo.excluded_resources.join(", ")}</strong>
          </p>
          {prepared?.excluded_resource_reasons.map((e) => (
            <p key={e.resource_id} className="reason-text">
              {e.resource_id}: {e.reason}
            </p>
          ))}
          <p className="reason-text">
            Remaining coverage: {prepared?.resources_touched.length} resource(s) — package will have reduced
            coverage of the original objective if executed.
          </p>
        </div>
      )}

      {recoverInfo && !recoverInfo.prepared && (
        <div className="recovery-card" style={{ borderColor: "var(--exception)" }}>
          <h3 style={{ color: "#ff9d96" }}>Recovery closed — nothing legitimate found</h3>
          <p className="reason-text">{recoverInfo.closed_reason}</p>
        </div>
      )}

      {executionFailed && (
        <div className="recovery-card" style={{ borderColor: "var(--exception)" }}>
          <h3 style={{ color: "#ff9d96" }}>Execution blocked</h3>
          <p className="reason-text">{executeResult.receipt.observed_effect}</p>
          <button className="button-secondary" onClick={onRecover} disabled={busy}>
            Propose a recovery route
          </button>
        </div>
      )}

      {executeResult?.receipt.executed && (
        <div className="manifest-box">
          <div className="mono" style={{ marginBottom: "0.4rem" }}>
            receipt {executeResult.receipt.hash.slice(0, 16)}…
          </div>
          {executeResult.manifest && executeResult.manifest.excluded_resources.length > 0 && (
            <p className="reason-text" style={{ color: "#ffbf8a" }}>
              Reduced coverage — excluded: {executeResult.manifest.excluded_resources.map((e) => e.resource_id).join(", ")}
            </p>
          )}
          {executeResult.manifest && (
            <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: "0.72rem" }}>
              {JSON.stringify(executeResult.manifest, null, 2)}
            </pre>
          )}
        </div>
      )}

      {!decision && !prepared && (
        <p className="reason-text section-gap">No pending action — click Prepare to propose one.</p>
      )}
    </section>
  );
}
