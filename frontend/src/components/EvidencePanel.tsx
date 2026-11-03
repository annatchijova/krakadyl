import type { EvidenceItem } from "../api";

function Badge({ kind, children }: { kind: "ok" | "error" | "pending" | "neutral"; children: React.ReactNode }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

export function EvidencePanel({ evidence }: { evidence: EvidenceItem[] }) {
  return (
    <section className="panel">
      <h2>Evidence</h2>
      {evidence.map((item) => (
        <div className="evidence-row" key={item.observation.id}>
          <div className="evidence-main">
            <div className="obs-id mono">
              {item.observation.id} <span style={{ color: "var(--text-muted)" }}>· {item.observation.source}</span>
            </div>
            <div className="obs-meta mono">digest {item.observation.digest.slice(0, 16)}…</div>
          </div>
          <div className="badges">
            <Badge kind={item.in_mandate_scope ? "ok" : "neutral"}>
              {item.in_mandate_scope ? "in scope" : "out of mandate"}
            </Badge>
            <Badge kind={item.integrity_ok ? "ok" : "error"}>
              {item.integrity_ok ? "integrity ok" : "integrity FAILED"}
            </Badge>
            {item.requirement_id && (
              <Badge kind={item.independently_verified ? "ok" : "pending"}>
                {item.independently_verified ? "verified" : `${item.requirement_status ?? "unverified"}`}
              </Badge>
            )}
            {!item.requirement_id && <Badge kind="neutral">no requirement</Badge>}
            {item.team_conflict && <Badge kind="error">team conflict</Badge>}
          </div>
        </div>
      ))}
    </section>
  );
}
