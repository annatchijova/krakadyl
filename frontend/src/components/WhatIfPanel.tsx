import { useEffect, useState } from "react";
import {
  counterfactualApi,
  teamApi,
  type CounterfactualOutcome,
  type CounterfactualView,
  type DeltaInput,
  type DeltaKind,
  type EvidenceRequirement,
} from "../api";

const fieldStyle: React.CSSProperties = {
  background: "var(--panel-raised)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "0.4rem",
  fontFamily: "inherit",
  fontSize: "0.8rem",
};

const KINDS: { kind: DeltaKind; label: string; needs: "value" | "requirement" | "until" | null }[] = [
  { kind: "grant_resource", label: "el mandato también cubriera el recurso…", needs: "value" },
  { kind: "grant_operation", label: "el mandato también permitiera la operación…", needs: "value" },
  { kind: "grant_destination", label: "el mandato también permitiera el destino…", needs: "value" },
  { kind: "extend_mandate_until", label: "el mandato fuera válido hasta…", needs: "until" },
  { kind: "mandate_not_revoked", label: "el mandato no estuviera revocado", needs: null },
  { kind: "requirement_verified", label: "este requisito estuviera verificado de forma independiente", needs: "requirement" },
  { kind: "requirement_unresolvable", label: "este requisito estuviera cerrado como irresoluble", needs: "requirement" },
  { kind: "conflict_resolved", label: "el conflicto de equipo sobre este requisito estuviera resuelto", needs: "requirement" },
  { kind: "source_available", label: "existiera una fuente autorizada para este requisito", needs: "requirement" },
];

function OutcomeBox({ title, outcome, hypothetical }: { title: string; outcome: CounterfactualOutcome; hypothetical: boolean }) {
  const kind = outcome.verdict === "allowed" ? "ok" : outcome.verdict === "forbidden" ? "error" : "warn";
  return (
    <div
      style={{
        flex: 1,
        minWidth: 200,
        border: hypothetical ? "2px dashed var(--inquiry)" : "1px solid var(--border)",
        background: hypothetical ? "rgba(102,84,192,0.08)" : "transparent",
        borderRadius: 8,
        padding: "0.6rem",
      }}
    >
      <div className="reason-text" style={{ fontWeight: 600, color: hypothetical ? "#c3b6ff" : undefined }}>{title}</div>
      <span className={`badge ${kind}`}>{outcome.verdict}</span>{" "}
      <span className="reason-text">
        evidencia {outcome.evidence_state} · autoridad {outcome.authority_state}
      </span>
      {outcome.would_include.length > 0 && <div className="reason-text">incluiría {outcome.would_include.join(", ")}</div>}
      <ul style={{ margin: "0.3rem 0 0 1rem", padding: 0, fontSize: "0.78rem" }}>
        {outcome.reasons.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
    </div>
  );
}

function label(d: DeltaInput) {
  return `${d.kind.replaceAll("_", " ")}${d.value ? ` ${d.value}` : ""}${d.requirement_id ? ` ${d.requirement_id}` : ""}${
    d.until ? ` ${new Date(d.until).toLocaleString()}` : ""
  }`;
}

export function WhatIfPanel({
  caseId,
  caseVersion,
  token,
}: {
  caseId: string;
  caseVersion: number;
  token: string;
}) {
  const [views, setViews] = useState<CounterfactualView[]>([]);
  const [requirements, setRequirements] = useState<EvidenceRequirement[]>([]);
  const [device, setDevice] = useState("device-A");
  const [destination, setDestination] = useState("reviewer-authorized");
  const [deltas, setDeltas] = useState<DeltaInput[]>([]);
  const [kind, setKind] = useState<DeltaKind>("grant_resource");
  const [value, setValue] = useState("");
  const [requirementId, setRequirementId] = useState("");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    counterfactualApi.list(caseId).then(setViews, (e) => setLocalError(String(e)));
    teamApi.overview(caseId).then((t) => setRequirements(t.requirements.map((r) => r.requirement)), (e) => setLocalError(String(e)));
  }, [caseId, caseVersion]);

  const needs = KINDS.find((k) => k.kind === kind)?.needs ?? null;

  function addDelta() {
    const delta: DeltaInput = { kind };
    if (needs === "value") delta.value = value.trim();
    if (needs === "requirement") delta.requirement_id = requirementId;
    if (needs === "until") delta.until = new Date(until).toISOString();
    setDeltas([...deltas, delta]);
    setValue("");
  }

  function evaluate() {
    setBusy(true);
    setLocalError(null);
    counterfactualApi
      .evaluate(caseId, token, { question: { allowed_device: device, destination }, deltas })
      .then(() => counterfactualApi.list(caseId))
      .then((v) => {
        setViews(v);
        setDeltas([]);
      })
      .catch((e) => setLocalError(String(e)))
      .finally(() => setBusy(false));
  }

  const latest = views[views.length - 1];
  const incomplete =
    (needs === "value" && !value.trim()) || (needs === "requirement" && !requirementId) || (needs === "until" && !until);

  return (
    <section className="panel" style={{ borderStyle: "dashed", borderColor: "var(--inquiry)" }}>
      <h2 style={{ color: "#c3b6ff" }}>¿Qué pasaría si…? (hipotético)</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        Corre los mismos chequeos sobre una copia del caso bajo los supuestos que elijas. Nunca cambia el caso, nunca
        produce nada ejecutable. Cada supuesto es un límite que alguien tendría que cambiar de verdad.
      </p>
      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
        <input style={fieldStyle} value={device} onChange={(e) => setDevice(e.target.value)} aria-label="device" />
        <input style={fieldStyle} value={destination} onChange={(e) => setDestination(e.target.value)} aria-label="destination" />
      </div>
      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginTop: 6 }}>
        <select style={fieldStyle} value={kind} onChange={(e) => setKind(e.target.value as DeltaKind)} aria-label="assumption">
          {KINDS.map((k) => (
            <option key={k.kind} value={k.kind}>
              si {k.label}
            </option>
          ))}
        </select>
        {needs === "value" && <input style={fieldStyle} value={value} onChange={(e) => setValue(e.target.value)} placeholder="ej. case-001/device-B" />}
        {needs === "requirement" && (
          <select style={fieldStyle} value={requirementId} onChange={(e) => setRequirementId(e.target.value)}>
            <option value="">requisito…</option>
            {requirements.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id}
              </option>
            ))}
          </select>
        )}
        {needs === "until" && <input type="datetime-local" style={fieldStyle} value={until} onChange={(e) => setUntil(e.target.value)} />}
        <button className="button-secondary" disabled={incomplete || deltas.length >= 8} onClick={addDelta}>
          Agregar supuesto
        </button>
      </div>
      {deltas.length > 0 && (
        <div className="badges" style={{ marginTop: 6 }}>
          {deltas.map((d, i) => (
            <span key={i} className="badge neutral" style={{ cursor: "pointer" }} onClick={() => setDeltas(deltas.filter((_, j) => j !== i))}>
              {label(d)} ✕
            </span>
          ))}
        </div>
      )}
      <div className="action-row">
        <button className="button-secondary" disabled={busy || !token || deltas.length === 0} onClick={evaluate}>
          Comparar con el caso real
        </button>
      </div>
      {localError && <p className="reason-text" style={{ color: "#ff9d96" }}>{localError}</p>}

      {latest && (
        <div className="section-gap">
          {latest.stale && (
            <p className="reason-text" style={{ color: "#ffbf8a" }}>
              El caso cambió después de calcular esto — ya no lo describe. Volvé a correrlo.
            </p>
          )}
          <p className="reason-text" style={{ margin: "0 0 0.3rem 0" }}>
            package_export de {latest.counterfactual.question.allowed_device} a {latest.counterfactual.question.destination} ·
            por {latest.counterfactual.created_by}
          </p>
          <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
            <OutcomeBox title="Caso real, ahora" outcome={latest.counterfactual.real} hypothetical={false} />
            <OutcomeBox title="HIPOTÉTICO — no es el caso" outcome={latest.counterfactual.hypothetical_outcome} hypothetical />
          </div>
          <div className="section-gap">
            {latest.counterfactual.effects.map((e, i) => (
              <div key={i} className="activity-item">
                <strong>si {label(e.delta)}</strong> —{" "}
                {e.necessary ? "necesario para este resultado hipotético" : "no hace falta para eso"}
                {e.sufficient_alone ? "; cambia el veredicto real por sí solo" : ""}
              </div>
            ))}
          </div>
          {views.length > 1 && <p className="reason-text">{views.length - 1} hipotético(s) anterior(es) guardado(s) en la actividad.</p>}
        </div>
      )}
    </section>
  );
}
