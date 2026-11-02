import type { CaseOverview } from "../api";

export function CaseSidebar({ overview }: { overview: CaseOverview }) {
  const { mission, mandate, hypotheses } = overview;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <section className="panel">
        <h2>Caso</h2>
        <p style={{ marginTop: 0 }}>{mission.objective}</p>
        <p className="reason-text">{mission.termination_criteria}</p>
        <div className="section-gap">
          <span className={`badge ${mandate.revoked ? "error" : "ok"}`}>
            {mandate.revoked ? "mandato revocado" : "mandato activo"}
          </span>
        </div>
        <p className="reason-text mono" style={{ marginTop: "0.6rem" }}>
          {mandate.resources.join(", ")} · {mandate.operations.join(", ")} → {mandate.destinations.join(", ")}
        </p>
        {mandate.revoked && <p className="reason-text">{mandate.revoked_reason}</p>}
        <p className="reason-text mono">revisión {mandate.revision}</p>
      </section>

      <section className="panel">
        <h2>Hipótesis</h2>
        {hypotheses.map((h) => (
          <div key={h.hypothesis.id} className="section-gap">
            <div className="badges" style={{ marginBottom: "0.3rem" }}>
              <span
                className={`badge ${
                  h.hypothesis.status === "accepted"
                    ? "ok"
                    : h.hypothesis.status === "rejected"
                      ? "neutral"
                      : "pending"
                }`}
              >
                {({ accepted: "aceptada", rejected: "rechazada", proposed: "propuesta" } as Record<string, string>)[
                  h.hypothesis.status
                ] ?? h.hypothesis.status}
              </span>
              {h.needs_review && <span className="badge warn">necesita revisión</span>}
            </div>
            <p style={{ margin: 0, fontSize: "0.85rem" }}>{h.hypothesis.explanation}</p>
            {h.needs_review && <p className="reason-text">{h.review_reason}</p>}
          </div>
        ))}
      </section>
    </div>
  );
}
