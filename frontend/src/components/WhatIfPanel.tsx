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
  { kind: "grant_resource", label: "the mandate also covered resource…", needs: "value" },
  { kind: "grant_operation", label: "the mandate also allowed operation…", needs: "value" },
  { kind: "grant_destination", label: "the mandate also allowed destination…", needs: "value" },
  { kind: "extend_mandate_until", label: "the mandate were valid until…", needs: "until" },
  { kind: "mandate_not_revoked", label: "the mandate were not revoked", needs: null },
  { kind: "requirement_verified", label: "this requirement were independently verified", needs: "requirement" },
  { kind: "requirement_unresolvable", label: "this requirement were closed as unresolvable", needs: "requirement" },
  { kind: "conflict_resolved", label: "the team conflict on this requirement were resolved", needs: "requirement" },
  { kind: "source_available", label: "an authorized source existed for this requirement", needs: "requirement" },
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
        evidence {outcome.evidence_state} · authority {outcome.authority_state}
      </span>
      {outcome.would_include.length > 0 && <div className="reason-text">would include {outcome.would_include.join(", ")}</div>}
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
      <h2 style={{ color: "#c3b6ff" }}>What if… (hypothetical)</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        Runs the same checks on a copy of the case under assumptions you choose. Never changes the case, never produces
        anything executable. Each assumption is a limit someone would have to change for real.
      </p>
      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
        <input style={fieldStyle} value={device} onChange={(e) => setDevice(e.target.value)} aria-label="device" />
        <input style={fieldStyle} value={destination} onChange={(e) => setDestination(e.target.value)} aria-label="destination" />
      </div>
      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginTop: 6 }}>
        <select style={fieldStyle} value={kind} onChange={(e) => setKind(e.target.value as DeltaKind)} aria-label="assumption">
          {KINDS.map((k) => (
            <option key={k.kind} value={k.kind}>
              if {k.label}
            </option>
          ))}
        </select>
        {needs === "value" && <input style={fieldStyle} value={value} onChange={(e) => setValue(e.target.value)} placeholder="e.g. case-001/device-B" />}
        {needs === "requirement" && (
          <select style={fieldStyle} value={requirementId} onChange={(e) => setRequirementId(e.target.value)}>
            <option value="">requirement…</option>
            {requirements.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id}
              </option>
            ))}
          </select>
        )}
        {needs === "until" && <input type="datetime-local" style={fieldStyle} value={until} onChange={(e) => setUntil(e.target.value)} />}
        <button className="button-secondary" disabled={incomplete || deltas.length >= 8} onClick={addDelta}>
          Add assumption
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
          Compare with the real case
        </button>
      </div>
      {localError && <p className="reason-text" style={{ color: "#ff9d96" }}>{localError}</p>}

      {latest && (
        <div className="section-gap">
          {latest.stale && (
            <p className="reason-text" style={{ color: "#ffbf8a" }}>
              The case changed after this was computed — it no longer describes the case. Run it again.
            </p>
          )}
          <p className="reason-text" style={{ margin: "0 0 0.3rem 0" }}>
            package_export of {latest.counterfactual.question.allowed_device} to {latest.counterfactual.question.destination} ·
            by {latest.counterfactual.created_by}
          </p>
          <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
            <OutcomeBox title="Real case, now" outcome={latest.counterfactual.real} hypothetical={false} />
            <OutcomeBox title="HYPOTHETICAL — not the case" outcome={latest.counterfactual.hypothetical_outcome} hypothetical />
          </div>
          <div className="section-gap">
            {latest.counterfactual.effects.map((e, i) => (
              <div key={i} className="activity-item">
                <strong>if {label(e.delta)}</strong> —{" "}
                {e.necessary ? "necessary for this hypothetical outcome" : "not needed for it"}
                {e.sufficient_alone ? "; changes the real verdict on its own" : ""}
              </div>
            ))}
          </div>
          {views.length > 1 && <p className="reason-text">{views.length - 1} earlier hypothetical(s) kept in the activity log.</p>}
        </div>
      )}
    </section>
  );
}
