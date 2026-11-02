import { useEffect, useMemo, useState } from "react";
import { delegationApi, type DelegateBody, type DelegationMandate, type DelegationView } from "../api";

const field: React.CSSProperties = {
  background: "var(--panel-raised)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "0.4rem",
  fontFamily: "inherit",
  fontSize: "0.8rem",
};

type ParentScope = {
  id: string;
  label: string;
  resources: string[];
  operations: string[];
  destinations: string[];
  valid_until: string | null;
};

function Chips({ items }: { items: string[] }) {
  return (
    <span className="badges" style={{ gap: "0.3rem" }}>
      {items.map((i) => (
        <span key={i} className="badge neutral mono" style={{ fontSize: "0.72rem" }}>
          {i}
        </span>
      ))}
    </span>
  );
}

function Chain({ chain }: { chain: string[] }) {
  // chain is leaf -> root; render root -> leaf as a path.
  const rootFirst = [...chain].reverse();
  return (
    <div className="reason-text mono" style={{ fontSize: "0.72rem", marginTop: "0.2rem" }}>
      {rootFirst.map((id, i) => (
        <span key={id}>
          {i > 0 && <span style={{ color: "var(--text-muted)" }}> → </span>}
          <span style={{ color: i === rootFirst.length - 1 ? "var(--signal)" : "var(--text-muted)" }}>{id}</span>
        </span>
      ))}
    </div>
  );
}

function ScopePicker({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: string[];
  selected: Set<string>;
  onToggle: (v: string) => void;
}) {
  return (
    <div style={{ minWidth: 150 }}>
      <div className="reason-text" style={{ fontWeight: 600, marginBottom: "0.2rem" }}>
        {label}
      </div>
      {options.map((o) => (
        <label key={o} style={{ display: "flex", gap: "0.35rem", alignItems: "center", fontSize: "0.78rem" }}>
          <input type="checkbox" checked={selected.has(o)} onChange={() => onToggle(o)} />
          <span className="mono" style={{ fontSize: "0.72rem" }}>
            {o}
          </span>
        </label>
      ))}
    </div>
  );
}

export function DelegationPanel({
  caseId,
  caseVersion,
  token,
  rootMandate,
  onChanged,
}: {
  caseId: string;
  caseVersion: number;
  token: string;
  rootMandate: { id: string; principal: string; resources: string[]; operations: string[]; destinations: string[]; valid_until?: string | null };
  onChanged: () => void;
}) {
  const [views, setViews] = useState<DelegationView[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [parentId, setParentId] = useState(rootMandate.id);
  const [principal, setPrincipal] = useState("");
  const [resources, setResources] = useState<Set<string>>(() => new Set(rootMandate.resources));
  const [operations, setOperations] = useState<Set<string>>(() => new Set(rootMandate.operations));
  const [destinations, setDestinations] = useState<Set<string>>(() => new Set(rootMandate.destinations));
  const [validUntil, setValidUntil] = useState(() => (rootMandate.valid_until ? toLocal(rootMandate.valid_until) : ""));

  useEffect(() => {
    delegationApi.list(caseId).then(setViews, (e) => setLocalError(String(e)));
  }, [caseId, caseVersion]);

  // Candidate parents you can delegate FROM: the case root, plus any live
  // delegation. You can only narrow a parent's scope, never widen it, so the
  // form offers exactly the parent's own resources/operations/destinations.
  const parents = useMemo<ParentScope[]>(() => {
    const live = views.filter((v) => v.live).map((v) => scopeOf(v.mandate, `${v.mandate.id} — to ${v.mandate.principal}`));
    return [scopeOf(rootMandate as DelegationMandate, `${rootMandate.id} (raíz del caso)`), ...live];
  }, [views, rootMandate]);

  const parent = parents.find((p) => p.id === parentId) ?? parents[0];

  // Choosing a parent defaults the new slice to that parent's full scope (the
  // widest a sub may have) and its deadline — updated from the selection event,
  // not an effect, since nothing external needs synchronizing.
  function selectParent(id: string) {
    setParentId(id);
    const next = parents.find((p) => p.id === id);
    if (!next) return;
    setResources(new Set(next.resources));
    setOperations(new Set(next.operations));
    setDestinations(new Set(next.destinations));
    setValidUntil(next.valid_until ? toLocal(next.valid_until) : "");
  }

  function toggle(setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  function delegate() {
    if (!parent) return;
    setBusy(true);
    setLocalError(null);
    const body: DelegateBody = {
      principal: principal.trim(),
      resources: [...resources],
      operations: [...operations],
      destinations: [...destinations],
      valid_until: validUntil ? new Date(validUntil).toISOString() : parent.valid_until,
    };
    delegationApi
      .delegate(caseId, parentId, token, body)
      .then(() => delegationApi.list(caseId))
      .then((v) => {
        setViews(v);
        setPrincipal("");
        onChanged();
      })
      .catch((e) => setLocalError(String(e)))
      .finally(() => setBusy(false));
  }

  const canDelegate =
    !!token &&
    !!principal.trim() &&
    resources.size > 0 &&
    operations.size > 0 &&
    destinations.size > 0;

  return (
    <section className="panel">
      <h2>Delegación — quién puede actuar, y hasta dónde</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        Un sub-mandato entrega una porción estrictamente más chica de autoridad a otro investigador. Nunca puede ser
        más amplio que su padre, y muere apenas cualquier mandato por encima se revoca o expira.
      </p>

      {views.length === 0 ? (
        <p className="reason-text" style={{ color: "var(--text-muted)" }}>Todavía no hay delegaciones.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {views.map((v) => (
            <div
              key={v.mandate.id}
              style={{
                border: `1px solid ${v.live ? "var(--border)" : "var(--exception)"}`,
                borderRadius: 8,
                padding: "0.55rem 0.65rem",
                background: v.live ? "var(--panel-raised)" : "rgba(173,61,54,0.08)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                <strong style={{ fontSize: "0.85rem" }}>a {v.mandate.principal}</strong>
                <span className={`badge ${v.live ? "ok" : "error"}`}>{v.live ? "vigente" : "sin vigencia"}</span>
              </div>
              <div style={{ marginTop: "0.35rem", display: "flex", flexWrap: "wrap", gap: "0.25rem 0.6rem" }}>
                <Chips items={v.mandate.resources} />
                <Chips items={v.mandate.operations} />
                <Chips items={v.mandate.destinations} />
              </div>
              <Chain chain={v.chain} />
              {!v.live && (
                <div className="reason-text" style={{ color: "#ff9d96", marginTop: "0.2rem" }}>
                  {v.status}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="section-gap" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.7rem" }}>
        <div className="reason-text" style={{ fontWeight: 600, marginBottom: "0.4rem" }}>Delegar una porción más chica</div>
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <label className="reason-text" style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
            desde el mandato
            <select style={field} value={parentId} onChange={(e) => selectParent(e.target.value)}>
              {parents.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="reason-text" style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
            a investigador
            <input style={field} value={principal} onChange={(e) => setPrincipal(e.target.value)} placeholder="ej. investigador-J" />
          </label>
          <label className="reason-text" style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
            válido hasta
            <input type="datetime-local" style={field} value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
          </label>
        </div>
        {parent && (
          <div style={{ display: "flex", gap: "1.2rem", flexWrap: "wrap" }}>
            <ScopePicker label="recursos" options={parent.resources} selected={resources} onToggle={(v) => toggle(setResources, v)} />
            <ScopePicker label="operaciones" options={parent.operations} selected={operations} onToggle={(v) => toggle(setOperations, v)} />
            <ScopePicker label="destinos" options={parent.destinations} selected={destinations} onToggle={(v) => toggle(setDestinations, v)} />
          </div>
        )}
        <div className="action-row">
          <button className="button-secondary" disabled={busy || !canDelegate} onClick={delegate}>
            Delegar
          </button>
          <span className="reason-text" style={{ color: "var(--text-muted)" }}>
            Solo {rootMandate.principal} (quien tiene el mandato) puede delegar desde la raíz.
          </span>
        </div>
        {localError && (
          <p className="reason-text" style={{ color: "#ff9d96" }}>
            {localError}
          </p>
        )}
      </div>
    </section>
  );
}

function scopeOf(m: DelegationMandate, label: string): ParentScope {
  return {
    id: m.id,
    label,
    resources: m.resources,
    operations: m.operations,
    destinations: m.destinations,
    valid_until: m.valid_until ?? null,
  };
}

function toLocal(iso: string): string {
  // datetime-local wants YYYY-MM-DDTHH:mm in local time.
  const d = new Date(iso);
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
}
