import { useEffect, useState } from "react";
import {
  teamApi,
  type ClaimKind,
  type Conflict,
  type EvidenceItem,
  type HandoffItem,
  type HandoffView,
  type TeamOverview,
  type TeamRequirementView,
} from "../api";

const fieldStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--panel-raised)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "0.45rem",
  fontFamily: "inherit",
  fontSize: "0.82rem",
  boxSizing: "border-box",
};

const KINDS: { value: ClaimKind; label: string }[] = [
  { value: "acknowledged", label: "Me hago responsable (dueño)" },
  { value: "reported_done", label: "Lo hice" },
  { value: "blocked", label: "Estoy bloqueado" },
  { value: "verified", label: "Chequeé de forma independiente lo que otro afirmó" },
  { value: "disputed", label: "Esto no es lo que dice el registro" },
];

function Section({ title, items, kind }: { title: string; items: HandoffItem[]; kind: string }) {
  if (items.length === 0) return null;
  return (
    <div className="section-gap">
      <div className="reason-text" style={{ fontWeight: 600 }}>
        {title} <span className={`badge ${kind}`}>{items.length}</span>
      </div>
      {items.map((i) => (
        <div key={i.requirement_id} className="activity-item" style={{ marginTop: 4 }}>
          <strong className="mono">{i.requirement_id}</strong> · owner {i.owner}
          {i.minutes_left != null && <> · {Math.round(i.minutes_left)} min left</>}
          <div>{i.summary}</div>
        </div>
      ))}
    </div>
  );
}

function ConflictCard({
  conflict,
  requirement,
  busy,
  canAct,
  onResolve,
}: {
  conflict: Conflict;
  requirement: TeamRequirementView | undefined;
  busy: boolean;
  canAct: boolean;
  onResolve: (conflict: Conflict, revision: string, decision: "keep_current_state" | "reopen_requirement", why: string) => void;
}) {
  const [why, setWhy] = useState("");
  return (
    <div className="recovery-card" style={{ borderColor: "var(--exception)", background: "rgba(173,61,54,0.12)" }}>
      <h3 style={{ color: "#ffd6d2" }}>
        Conflicto · {conflict.kind.replaceAll("_", " ")} · <span className="mono">{conflict.requirement_id}</span>
      </h3>
      <p style={{ margin: 0, fontSize: "0.84rem" }}>{conflict.description}</p>
      <p className="reason-text" style={{ margin: "0.3rem 0" }}>
        registros {conflict.record_ids.join(", ")} · involucrados: {conflict.parties.join(", ")} — lo resuelve otra persona.
      </p>
      {requirement && (
        <>
          <input style={fieldStyle} value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Qué chequeaste para resolverlo" />
          <div className="action-row">
            <button
              className="button-secondary"
              disabled={busy || !canAct || !why.trim() || conflict.kind === "evidence_mismatch"}
              onClick={() => onResolve(conflict, requirement.requirement_revision, "keep_current_state", why)}
            >
              Mantener el estado actual
            </button>
            <button
              className="button-danger"
              disabled={busy || !canAct || !why.trim()}
              onClick={() => onResolve(conflict, requirement.requirement_revision, "reopen_requirement", why)}
            >
              Reabrir el requisito
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function TeamPanel({
  caseId,
  caseVersion,
  token,
  evidence,
  onChanged,
}: {
  caseId: string;
  caseVersion: number;
  token: string;
  evidence: EvidenceItem[];
  onChanged: () => Promise<void>;
}) {
  const [team, setTeam] = useState<TeamOverview | null>(null);
  const [view, setView] = useState<HandoffView | null>(null);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const [requirementId, setRequirementId] = useState("");
  const [kind, setKind] = useState<ClaimKind>("reported_done");
  const [statement, setStatement] = useState("");
  const [evidenceId, setEvidenceId] = useState("");
  const [refersTo, setRefersTo] = useState("");
  const [method, setMethod] = useState("");

  const [toActor, setToActor] = useState("");
  const [transfer, setTransfer] = useState<string[]>([]);
  const [note, setNote] = useState("");

  const reload = () =>
    Promise.all([teamApi.overview(caseId), teamApi.handoff(caseId)]).then(([t, h]) => {
      setTeam(t);
      setView(h);
    });

  useEffect(() => {
    reload().catch((e) => setLocalError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, caseVersion]);

  function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setLocalError(null);
    fn()
      .catch((e) => setLocalError(String(e)))
      .then(() => Promise.all([reload(), onChanged()]))
      .catch((e) => setLocalError(String(e)))
      .finally(() => setBusy(false));
  }

  if (!team || !view) return null;
  const h = view.handoff;
  const selected = team.requirements.find((r) => r.requirement.id === requirementId);
  const recordsForSelected = team.records.filter((r) => r.requirement_id === requirementId);
  const canAct = team.enabled && token.length > 0;

  function submitStatement() {
    if (!selected) return;
    const item = evidence.find((e) => e.observation.id === evidenceId);
    run(() =>
      teamApi.say(caseId, selected.requirement.id, token, {
        kind,
        statement,
        expected_requirement_revision: selected.requirement_revision,
        evidence_refs: item ? [{ kind: "observation", ref_id: item.observation.id, digest: item.observation.digest }] : [],
        refers_to: refersTo ? [refersTo] : [],
        verification_method: kind === "verified" ? method : null,
      }).then(() => {
        setStatement("");
        setMethod("");
      }),
    );
  }

  const resolve = (conflict: Conflict, revision: string, decision: "keep_current_state" | "reopen_requirement", why: string) =>
    run(() =>
      teamApi.say(caseId, conflict.requirement_id, token, {
        kind: "resolution",
        statement: why,
        expected_requirement_revision: revision,
        refers_to: [...conflict.record_ids],
        resolves_conflict_id: conflict.conflict_id,
        decision,
      }),
    );

  return (
    <section className="panel">
      <h2>Equipo y traspaso de turno</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        Lo que hay que saber para retomar este caso, solo desde el estado registrado. El “hecho” de un compañero es una afirmación hasta que otro lo chequea;
        los desacuerdos aparecen acá en vez de sobrescribirse.
      </p>
      {localError && <p className="reason-text" style={{ color: "#ff9d96" }}>{localError}</p>}

      {Object.entries(view.pending_for).map(([who, ids]) =>
        ids.map((id) => {
          const event = view.events.find((e) => e.event_id === id);
          return (
            <div key={id} className="recovery-card">
              <h3>Traspaso esperando a {who}</h3>
              <p style={{ margin: 0, fontSize: "0.84rem" }}>
                de {event?.actor}: {event?.note || "(sin nota)"} · {event?.transfer.length ?? 0} requisito(s) para tomar
              </p>
              <div className="action-row">
                <button className="button-primary" disabled={busy || !canAct} onClick={() => run(() => teamApi.accept(caseId, id, token))}>
                  Aceptar (con tu token)
                </button>
              </div>
            </div>
          );
        }),
      )}

      {h.open_conflicts.map((c) => (
        <ConflictCard
          key={c.conflict_id}
          conflict={c}
          requirement={team.requirements.find((r) => r.requirement.id === c.requirement_id)}
          busy={busy}
          canAct={canAct}
          onResolve={resolve}
        />
      ))}
      <Section title="Declarado, sin verificar — ventana cerrándose" items={h.urgent_unverified} kind="error" />
      <Section title="Declarado, sin verificar" items={h.claimed_unverified} kind="pending" />
      <Section title="Asignado, sin reconocer" items={h.not_acknowledged} kind="warn" />
      <Section title="Bloqueado" items={h.blocked} kind="warn" />
      <Section title="Estado desconocido" items={h.uncertain_status} kind="neutral" />
      {h.acquisitions_in_flight.length > 0 && (
        <p className="reason-text">
          Adquisiciones sin resolver: {h.acquisitions_in_flight.map((a) => `${a.requirement_id} (${a.state})`).join(", ")}
        </p>
      )}
      {h.hypotheses_needing_review.length > 0 && (
        <p className="reason-text">Hipótesis para revisar: {h.hypotheses_needing_review.map(([id]) => id).join(", ")}</p>
      )}
      <p className="reason-text">
        Verificados: {h.verified.length} · cerrados como irresolubles: {h.closed_unresolvable.length} · próximo paso:{" "}
        {h.next_move.primary ?? (h.next_move.uncertain ? "sin una prioridad defendible única" : "ninguno")}
      </p>

      <div className="section-gap" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.7rem" }}>
        <div className="reason-text" style={{ fontWeight: 600 }}>Registrar una declaración</div>
        <select style={fieldStyle} value={requirementId} onChange={(e) => setRequirementId(e.target.value)}>
          <option value="">Elegí un requisito…</option>
          {team.requirements.map((r) => (
            <option key={r.requirement.id} value={r.requirement.id}>
              {r.requirement.id} — {r.requirement.responsibility.status}
              {r.open_conflicts.length ? " — CONFLICTO" : ""}
            </option>
          ))}
        </select>
        {selected && (
          <>
            <select style={{ ...fieldStyle, marginTop: 4 }} value={kind} onChange={(e) => setKind(e.target.value as ClaimKind)}>
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
            <textarea
              style={{ ...fieldStyle, marginTop: 4 }}
              rows={2}
              value={statement}
              onChange={(e) => setStatement(e.target.value)}
              placeholder="En tus palabras"
            />
            {(kind === "reported_done" || kind === "verified") && (
              <select style={{ ...fieldStyle, marginTop: 4 }} value={evidenceId} onChange={(e) => setEvidenceId(e.target.value)}>
                <option value="">Sin evidencia adjunta</option>
                {evidence.map((e) => (
                  <option key={e.observation.id} value={e.observation.id}>
                    adjuntar {e.observation.id} (sha256 {e.observation.digest.slice(0, 12)}…)
                  </option>
                ))}
              </select>
            )}
            {(kind === "verified" || kind === "disputed") && (
              <select style={{ ...fieldStyle, marginTop: 4 }} value={refersTo} onChange={(e) => setRefersTo(e.target.value)}>
                <option value="">{kind === "disputed" ? "El estado registrado actual" : "Elegí la afirmación que chequeaste…"}</option>
                {recordsForSelected
                  .filter((r) => r.kind === "reported_done" || (kind === "disputed" && r.kind === "verified"))
                  .map((r) => (
                    <option key={r.record_id} value={r.record_id}>
                      {r.kind} por {r.actor}: {r.statement.slice(0, 60)}
                    </option>
                  ))}
              </select>
            )}
            {kind === "verified" && (
              <input
                style={{ ...fieldStyle, marginTop: 4 }}
                value={method}
                onChange={(e) => setMethod(e.target.value)}
                placeholder="Cómo lo chequeaste (ej. re-hasheé la copia compartida)"
              />
            )}
            <div className="action-row">
              <button
                className="button-secondary"
                disabled={busy || !canAct || !statement.trim() || (kind === "verified" && (!method.trim() || !refersTo))}
                onClick={submitStatement}
              >
                Registrar (como dueño del token)
              </button>
            </div>
          </>
        )}
      </div>

      <div className="section-gap" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.7rem" }}>
        <div className="reason-text" style={{ fontWeight: 600 }}>Traspasar este turno</div>
        <select style={fieldStyle} value={toActor} onChange={(e) => setToActor(e.target.value)}>
          <option value="">A…</option>
          {team.operators.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
        {team.requirements
          .filter((r) => !r.requirement.resolved && !r.requirement.unresolvable)
          .map((r) => (
            <label key={r.requirement.id} className="reason-text" style={{ display: "flex", gap: "0.4rem", marginTop: 4 }}>
              <input
                type="checkbox"
                checked={transfer.includes(r.requirement.id)}
                onChange={(e) =>
                  setTransfer(e.target.checked ? [...transfer, r.requirement.id] : transfer.filter((x) => x !== r.requirement.id))
                }
              />
              traspasar {r.requirement.id} (dueño {r.requirement.responsibility.owner})
            </label>
          ))}
        <textarea
          style={{ ...fieldStyle, marginTop: 4 }}
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Algo que la próxima persona necesite y no esté registrado arriba"
        />
        <p className="reason-text" style={{ margin: "0.3rem 0" }}>
          Se ata exactamente a la vista de arriba (estado {h.state_digest.slice(0, 12)}…). La responsabilidad se mueve; la
          autoridad de captura y export no.
        </p>
        <div className="action-row">
          <button
            className="button-primary"
            disabled={busy || !canAct || !toActor}
            onClick={() =>
              run(() =>
                teamApi
                  .handOver(caseId, token, {
                    to_actor: toActor,
                    seen_state_digest: h.state_digest,
                    transfer_requirement_ids: transfer,
                    note,
                  })
                  .then(() => {
                    setTransfer([]);
                    setNote("");
                  }),
              )
            }
          >
            Traspasar
          </button>
        </div>
      </div>
    </section>
  );
}
