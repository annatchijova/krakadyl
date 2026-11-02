import { useEffect, useState } from "react";
import { delegationApi, type ResumeBriefing, type ResumeGapItem } from "../api";

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}

export function ResumePanel({ caseId, caseVersion }: { caseId: string; caseVersion: number }) {
  const [briefing, setBriefing] = useState<ResumeBriefing | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    delegationApi.resume(caseId).then(setBriefing, (e) => setLocalError(String(e)));
  }, [caseId, caseVersion]);

  if (localError) {
    return (
      <section className="panel">
        <h2>Retomando donde lo dejaste</h2>
        <p className="reason-text" style={{ color: "#ff9d96" }}>{localError}</p>
      </section>
    );
  }
  if (!briefing) {
    return (
      <section className="panel">
        <h2>Retomando donde lo dejaste</h2>
        <p className="reason-text">Cargando…</p>
      </section>
    );
  }

  const nothingLapsed =
    briefing.mandates_expired_while_away.length === 0 && briefing.recovery_closed_while_away.length === 0;

  return (
    <section className="panel">
      <h2>Retomando donde lo dejaste</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        Qué cambió en este caso mientras no estabas, desde la última actividad registrada (hace {briefing.gap_human}) hasta
        ahora — por el solo paso del tiempo, nada que tengas que reconstruir a mano.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
        <div>
          <div className="reason-text" style={{ fontWeight: 700, color: nothingLapsed ? "#8fe6c9" : "#ff9d96" }}>
            {nothingLapsed ? "No caducó nada mientras no estabas." : "Caducó mientras no estabas"}
          </div>
          {briefing.mandates_expired_while_away.length > 0 && (
            <ul className="tight-list">
              {briefing.mandates_expired_while_away.map((id) => (
                <li key={id}>
                  <span className="badge error">expiró</span>{" "}
                  <span className="mono">{id}</span>
                  {briefing.delegations_expired_while_away.includes(id) && (
                    <span className="reason-text"> — una delegación que otorgaste caducó</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {briefing.recovery_closed_while_away.length > 0 && (
            <ul className="tight-list">
              {briefing.recovery_closed_while_away.map((it: ResumeGapItem) => (
                <li key={it.requirement_id}>
                  <span className="badge error">ventana cerrada</span>{" "}
                  <span className="mono">{it.requirement_id}</span> — se perdió {it.what_is_lost_if_missed}{" "}
                  <span className="reason-text">(cerró {when(it.at)})</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {briefing.recovery_still_open.length > 0 && (
          <div>
            <div className="reason-text" style={{ fontWeight: 700 }}>Todavía rescatable — primero lo más urgente</div>
            <ul className="tight-list">
              {briefing.recovery_still_open.map((it, i) => (
                <li key={it.requirement_id}>
                  <span className={`badge ${i === 0 ? "warn" : "neutral"}`}>{i === 0 ? "más urgente" : "abierto"}</span>{" "}
                  <span className="mono">{it.requirement_id}</span> — hasta {when(it.at)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {briefing.conditional_or_unknown_watch.length > 0 && (
          <div>
            <div className="reason-text" style={{ fontWeight: 700 }}>En observación — no se puede ordenar por tiempo</div>
            <p className="reason-text" style={{ margin: "0.1rem 0" }}>
              Abierto, pero la ventana es condicional o desconocida — se muestra para que no se hunda en silencio:
            </p>
            <span className="badges">
              {briefing.conditional_or_unknown_watch.map((id) => (
                <span key={id} className="badge neutral mono" style={{ fontSize: "0.72rem" }}>{id}</span>
              ))}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
