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
        <h2>Picking up where you left off</h2>
        <p className="reason-text" style={{ color: "#ff9d96" }}>{localError}</p>
      </section>
    );
  }
  if (!briefing) {
    return (
      <section className="panel">
        <h2>Picking up where you left off</h2>
        <p className="reason-text">Loading…</p>
      </section>
    );
  }

  const nothingLapsed =
    briefing.mandates_expired_while_away.length === 0 && briefing.recovery_closed_while_away.length === 0;

  return (
    <section className="panel">
      <h2>Picking up where you left off</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        What changed on this case while you were away, from the last recorded activity ({briefing.gap_human} ago) to now —
        caused by time alone, nothing you have to reconstruct by hand.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
        <div>
          <div className="reason-text" style={{ fontWeight: 700, color: nothingLapsed ? "#8fe6c9" : "#ff9d96" }}>
            {nothingLapsed ? "Nothing lapsed while you were away." : "Lapsed while you were away"}
          </div>
          {briefing.mandates_expired_while_away.length > 0 && (
            <ul className="tight-list">
              {briefing.mandates_expired_while_away.map((id) => (
                <li key={id}>
                  <span className="badge error">expired</span>{" "}
                  <span className="mono">{id}</span>
                  {briefing.delegations_expired_while_away.includes(id) && (
                    <span className="reason-text"> — a delegation you granted has lapsed</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {briefing.recovery_closed_while_away.length > 0 && (
            <ul className="tight-list">
              {briefing.recovery_closed_while_away.map((it: ResumeGapItem) => (
                <li key={it.requirement_id}>
                  <span className="badge error">window closed</span>{" "}
                  <span className="mono">{it.requirement_id}</span> — lost {it.what_is_lost_if_missed}{" "}
                  <span className="reason-text">(closed {when(it.at)})</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {briefing.recovery_still_open.length > 0 && (
          <div>
            <div className="reason-text" style={{ fontWeight: 700 }}>Still savable — soonest first</div>
            <ul className="tight-list">
              {briefing.recovery_still_open.map((it, i) => (
                <li key={it.requirement_id}>
                  <span className={`badge ${i === 0 ? "warn" : "neutral"}`}>{i === 0 ? "most urgent" : "open"}</span>{" "}
                  <span className="mono">{it.requirement_id}</span> — until {when(it.at)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {briefing.conditional_or_unknown_watch.length > 0 && (
          <div>
            <div className="reason-text" style={{ fontWeight: 700 }}>On watch — can't be time-ranked</div>
            <p className="reason-text" style={{ margin: "0.1rem 0" }}>
              Open, but the window is conditional or unknown — surfaced so it doesn't quietly sink:
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
