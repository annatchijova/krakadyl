import { useState } from "react";
import type { LayaSignals } from "../api";

function SignalBar({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ marginBottom: "0.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.78rem" }}>
        <span className="reason-text">{label}</span>
        <span className="mono">{value.toFixed(2)}</span>
      </div>
      <div style={{ background: "var(--border)", borderRadius: 4, height: 6, overflow: "hidden" }}>
        <div
          style={{
            width: `${Math.round(value * 100)}%`,
            background: "var(--inquiry)",
            height: "100%",
          }}
        />
      </div>
    </div>
  );
}

export function LayaNotePanel({
  busy,
  onAnalyze,
}: {
  busy: boolean;
  onAnalyze: (noteText: string) => Promise<LayaSignals>;
}) {
  const [noteText, setNoteText] = useState("");
  const [signals, setSignals] = useState<LayaSignals | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  async function handleAnalyze() {
    setLocalError(null);
    try {
      const result = await onAnalyze(noteText);
      setSignals(result);
    } catch (e) {
      setLocalError(String(e));
    }
  }

  return (
    <section className="panel">
      <h2>Nota de traspaso (Laya)</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        Solo señales tipadas — Laya nunca marca nada como verificado. Señala lo que un humano debería revisar.
      </p>
      <textarea
        value={noteText}
        onChange={(e) => setNoteText(e.target.value)}
        placeholder="Pegá una nota de traspaso o mensaje, ej. 'obs-a1 hecho, nadie más lo miró todavía'"
        rows={3}
        style={{
          width: "100%",
          background: "var(--panel-raised)",
          color: "var(--text)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "0.5rem",
          fontFamily: "inherit",
          fontSize: "0.82rem",
          resize: "vertical",
        }}
      />
      <div className="action-row">
        <button
          className="button-secondary"
          onClick={handleAnalyze}
          disabled={busy || noteText.trim().length === 0}
        >
          Analizar con Laya
        </button>
      </div>
      {localError && <p className="reason-text" style={{ color: "#ff9d96" }}>{localError}</p>}
      {signals && (
        <div className="section-gap">
          <SignalBar label="afirma verificación independiente" value={signals.claims_independent_verification} />
          <SignalBar label="afirma tarea completa" value={signals.claims_task_complete} />
          <SignalBar label="urgencia" value={signals.urgency} />
          {signals.claims_task_complete > 0.5 && signals.claims_independent_verification < 0.4 && (
            <p className="reason-text" style={{ color: "#ffbf8a" }}>
              Se lee como un auto-reporte sin verificación independiente mencionada — conviene verificar antes de confiar.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
