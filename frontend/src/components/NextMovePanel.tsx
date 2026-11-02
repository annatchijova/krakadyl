import type { Decision, ExecuteResponse, PreparedAction, RecoverResponse } from "../api";

function verdictBadge(verdict: Decision["verdict"]) {
  const kind = verdict === "allowed" ? "ok" : verdict === "forbidden" ? "error" : "warn";
  const es: Record<string, string> = { allowed: "permitido", forbidden: "prohibido", confirm: "confirmar", gather_evidence: "reunir evidencia" };
  return <span className={`badge ${kind}`}>{es[verdict] ?? verdict}</span>;
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
      <h2>Próximo paso</h2>

      <div className="action-row">
        <button className="button-primary" onClick={onPrepare} disabled={busy}>
          Preparar package_export
        </button>
        <button className="button-secondary" onClick={onAskMuse} disabled={busy} title="Llamada real a Muse Spark — cuesta unos centavos">
          Preguntar a Muse
        </button>
        {canExecute && (
          <button className="button-secondary" onClick={() => onExecute(prepared!.id)} disabled={busy}>
            {isRecoveryReview ? "Ejecutar esta recuperación" : "Ejecutar"}
          </button>
        )}
      </div>

      {museReasoning && (
        <div className="recovery-card" style={{ borderColor: "var(--signal)", background: "rgba(214,255,127,0.06)" }}>
          <h3 style={{ color: "var(--signal)" }}>Muse dice (no es autoridad)</h3>
          <p style={{ margin: 0, fontSize: "0.85rem" }}>{museReasoning}</p>
          <p className="reason-text">
            Igual se chequea contra el mandato y la evidencia reales de abajo — es una propuesta, no una decisión.
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
          <div>recursos: {prepared.resources_touched.join(", ") || "(ninguno)"}</div>
          <div>destino: {prepared.destination}</div>
          <div>expira: {new Date(prepared.expires_at).toLocaleTimeString()}</div>
        </div>
      )}

      {isRecoveryReview && recoverInfo && (
        <div className="recovery-card">
          <h3>Propuesta de recuperación — revisá antes de ejecutar</h3>
          <p style={{ margin: "0 0 0.4rem 0", fontSize: "0.85rem" }}>
            Excluye exactamente: <strong>{recoverInfo.excluded_resources.join(", ")}</strong>
          </p>
          {prepared?.excluded_resource_reasons.map((e) => (
            <p key={e.resource_id} className="reason-text">
              {e.resource_id}: {e.reason}
            </p>
          ))}
          <p className="reason-text">
            Cobertura restante: {prepared?.resources_touched.length} recurso(s) — el paquete tendrá cobertura reducida
            del objetivo original si se ejecuta.
          </p>
        </div>
      )}

      {recoverInfo && !recoverInfo.prepared && (
        <div className="recovery-card" style={{ borderColor: "var(--exception)" }}>
          <h3 style={{ color: "#ff9d96" }}>Recuperación cerrada — no se encontró nada legítimo</h3>
          <p className="reason-text">{recoverInfo.closed_reason}</p>
        </div>
      )}

      {executionFailed && (
        <div className="recovery-card" style={{ borderColor: "var(--exception)" }}>
          <h3 style={{ color: "#ff9d96" }}>Ejecución bloqueada</h3>
          <p className="reason-text">{executeResult.receipt.observed_effect}</p>
          <button className="button-secondary" onClick={onRecover} disabled={busy}>
            Proponer una ruta de recuperación
          </button>
        </div>
      )}

      {executeResult?.receipt.executed && (
        <div className="manifest-box">
          <div className="mono" style={{ marginBottom: "0.4rem" }}>
            recibo {executeResult.receipt.hash.slice(0, 16)}…
          </div>
          {executeResult.manifest && executeResult.manifest.excluded_resources.length > 0 && (
            <p className="reason-text" style={{ color: "#ffbf8a" }}>
              Cobertura reducida — excluido: {executeResult.manifest.excluded_resources.map((e) => e.resource_id).join(", ")}
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
        <p className="reason-text section-gap">No hay acción pendiente — tocá Preparar para proponer una.</p>
      )}
    </section>
  );
}
