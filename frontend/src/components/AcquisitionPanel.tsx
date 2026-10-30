import { useEffect, useState } from "react";
import {
  acquisitionApi,
  type AcquisitionOverview,
  type AcquisitionRecordView,
  type AnnotationView,
  type EvaluationOutcome,
  type RouteView,
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

const OUTCOMES: { value: EvaluationOutcome; label: string }[] = [
  { value: "supports_requirement", label: "supports the requirement" },
  { value: "contradicts_requirement", label: "contradicts the requirement" },
  { value: "no_discriminating_change", label: "valid, but does not discriminate" },
  { value: "insufficient_or_invalid", label: "insufficient or invalid" },
];

function requirementBadge(route: RouteView) {
  const r = route.requirement;
  if (r.resolved) return <span className="badge ok">resolved · verified</span>;
  if (r.unresolvable) return <span className="badge neutral">closed as unresolvable</span>;
  if (r.responsibility.status === "reported_done") return <span className="badge pending">claimed, not verified</span>;
  return <span className="badge warn">open</span>;
}

function usd(micros: number) {
  return `$${(micros / 1_000_000).toFixed(4)}`;
}

function CaptureWithBoxes({ caseId, record, token }: { caseId: string; record: AcquisitionRecordView; token: string }) {
  const [annotation, setAnnotation] = useState<AnnotationView | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const workflowId = record.workflow.workflow_id;
  const hasAnnotation = record.annotation !== null;

  useEffect(() => {
    if (!token) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    acquisitionApi.observationObjectUrl(caseId, workflowId, token).then(
      (url) => {
        objectUrl = url;
        if (cancelled) URL.revokeObjectURL(url);
        else setImageUrl(url);
      },
      (e) => setLoadError(String(e)),
    );
    if (hasAnnotation) {
      acquisitionApi.annotation(caseId, workflowId, token).then(setAnnotation, (e) => setLoadError(String(e)));
    }
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [caseId, workflowId, hasAnnotation, token]);

  if (!token) {
    return <p className="reason-text">Enter an operator token to view the capture.</p>;
  }

  return (
    <div>
      <div style={{ position: "relative", maxWidth: 320 }}>
        {imageUrl && <img
          src={imageUrl}
          alt={`capture ${record.observation?.digest.slice(0, 12)}`}
          style={{ display: "block", width: "100%", borderRadius: 6, border: "1px solid var(--border)" }}
        />}
        {annotation && annotation.frame_width && annotation.frame_height && (
          <svg
            viewBox={`0 0 ${annotation.frame_width} ${annotation.frame_height}`}
            preserveAspectRatio="none"
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
          >
            {annotation.boxes.map((b) => (
              <rect
                key={b.object_id}
                x={b.x1}
                y={b.y1}
                width={b.x2_inclusive - b.x1 + 1}
                height={b.y2_inclusive - b.y1 + 1}
                fill="none"
                stroke="var(--signal)"
                strokeWidth={Math.max(annotation.frame_width!, annotation.frame_height!) / 160}
                strokeDasharray="4 2"
              />
            ))}
          </svg>
        )}
      </div>
      <div className="obs-meta mono reason-text" style={{ marginTop: 4 }}>
        observation sha256:{record.observation?.digest.slice(0, 16)}… · captured by {record.observation?.actor}
      </div>
      {hasAnnotation && (
        <p className="reason-text" style={{ margin: "0.3rem 0", color: "#ffbf8a" }}>
          SAM candidate ({annotation ? `${annotation.sidecar_status}, ${annotation.boxes.length} region(s)` : "loading"}) —{" "}
          {annotation?.trust ?? "untrusted model output"}
        </p>
      )}
      {loadError && <p className="reason-text" style={{ color: "#ff9d96" }}>{loadError}</p>}
    </div>
  );
}

function HistoryItem({
  caseId,
  record,
  route,
  busy,
  run,
  token,
}: {
  caseId: string;
  record: AcquisitionRecordView;
  route: RouteView;
  busy: boolean;
  run: (fn: () => Promise<unknown>) => void;
  token: string;
}) {
  const [outcome, setOutcome] = useState<EvaluationOutcome>("no_discriminating_change");
  const [criterion, setCriterion] = useState("clock-within-one-minute");
  const [rationale, setRationale] = useState("");
  const [reconcileNote, setReconcileNote] = useState("");
  const open = !route.requirement.resolved && !route.requirement.unresolvable;
  const unknown = record.attempts.filter((a) => a.state === "unknown_after_dispatch");

  return (
    <div className="recovery-card">
      <h3>
        Acquisition {record.workflow.workflow_id.slice(-8)} ·{" "}
        <span className={`badge ${record.state === "completed" ? "ok" : record.state === "unknown" ? "error" : "neutral"}`}>
          {record.state}
        </span>
      </h3>
      <p className="reason-text" style={{ margin: "0 0 0.4rem 0" }}>
        authorized by {record.workflow.actor_identity} · attempts:{" "}
        {record.attempts.map((a) => `${a.attempt.phase} ${a.state}`).join(", ")} · spent{" "}
        {usd(record.workflow.actual_usage.usd_micros)}
      </p>
      {record.observation && <CaptureWithBoxes caseId={caseId} record={record} token={token} />}

      {record.evaluations.map((e) => (
        <div key={e.evaluation_id} className="activity-item" style={{ marginTop: "0.4rem" }}>
          <strong>{e.evaluator_identity}</strong>: {e.outcome.replaceAll("_", " ")} — {e.rationale}
          <div className="ts mono">
            {e.criterion_id}@{e.criterion_version} · {e.evaluation_id}
          </div>
        </div>
      ))}

      {unknown.map((a) => (
        <div key={a.attempt.attempt_id} className="section-gap">
          <p className="reason-text" style={{ color: "#ff9d96", margin: 0 }}>
            {a.attempt.phase} outcome is UNKNOWN ({a.attempt.outcome_reason}). Nothing retries or refunds until a person
            reconciles it.
          </p>
          <input
            style={fieldStyle}
            value={reconcileNote}
            onChange={(e) => setReconcileNote(e.target.value)}
            placeholder="What did you check? (provider console, logs…)"
          />
          <div className="action-row">
            <button
              className="button-secondary"
              disabled={busy || !token || !reconcileNote.trim()}
              onClick={() =>
                run(() => acquisitionApi.reconcile(caseId, a.attempt.attempt_id, token, "accepted_as_unknown", reconcileNote))
              }
            >
              Accept as unknown
            </button>
            <button
              className="button-secondary"
              disabled={busy || !token || !reconcileNote.trim()}
              onClick={() =>
                run(() => acquisitionApi.reconcile(caseId, a.attempt.attempt_id, token, "confirmed_not_dispatched", reconcileNote))
              }
            >
              Confirmed never dispatched
            </button>
          </div>
        </div>
      ))}

      {(record.state === "completed" || record.state === "failed") && record.observation && open && (
        <div className="section-gap">
          <p className="reason-text" style={{ margin: "0 0 0.3rem 0" }}>
            Evaluate against: “{route.requirement.discriminating_question}”. Only an evaluator other than{" "}
            {record.workflow.actor_identity} can verify it; a self-evaluation is recorded as a claim.
          </p>
          <select style={fieldStyle} value={outcome} onChange={(e) => setOutcome(e.target.value as EvaluationOutcome)}>
            {OUTCOMES.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <input style={{ ...fieldStyle, marginTop: 4 }} value={criterion} onChange={(e) => setCriterion(e.target.value)} />
          <textarea
            style={{ ...fieldStyle, marginTop: 4 }}
            rows={2}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="What you saw in the capture, in your own words"
          />
          <div className="action-row">
            <button
              className="button-primary"
              disabled={busy || !token || !rationale.trim() || !criterion.trim()}
              onClick={() =>
                run(() =>
                  acquisitionApi.evaluate(caseId, record.workflow.workflow_id, token, {
                    expected_requirement_revision: route.requirement_revision,
                    criterion_id: criterion,
                    criterion_version: "1",
                    outcome,
                    rationale,
                  }),
                )
              }
            >
              Record evaluation
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function RequirementCard({
  caseId,
  route,
  overview,
  busy,
  run,
  token,
  loadedAtMs,
}: {
  caseId: string;
  route: RouteView;
  overview: AcquisitionOverview;
  busy: boolean;
  run: (fn: () => Promise<unknown>) => void;
  token: string;
  loadedAtMs: number;
}) {
  const requirement = route.requirement;
  const [instructions, setInstructions] = useState(`Photograph for: ${requirement.discriminating_question ?? ""}`);
  const [useSam, setUseSam] = useState(false);
  const [samPrompt, setSamPrompt] = useState("clock display");
  const [file, setFile] = useState<File | null>(null);
  const [abstainReason, setAbstainReason] = useState("");

  const usedAuthorizations = new Set(overview.history.map((h) => h.workflow.authorization_id));
  const proposals = overview.proposals.filter((p) => p.proposal.need.requirement_id === requirement.id);
  const authorizedProposalIds = new Set(overview.authorizations.map((a) => a.proposal_id));
  const pendingProposals = proposals.filter((p) => !authorizedProposalIds.has(p.id));
  const usableGrants = overview.authorizations.filter(
    (a) =>
      proposals.some((p) => p.id === a.proposal_id) &&
      !usedAuthorizations.has(a.authorization.authorization_id) &&
      new Date(a.authorization.expires_at).getTime() > loadedAtMs,
  );
  const history = overview.history.filter((h) => h.requirement_id === requirement.id);
  const open = !requirement.resolved && !requirement.unresolvable;
  const anyInFlight = history.some((h) => h.state === "active" || h.state === "unknown");

  return (
    <div className="section-gap" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.7rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
        <strong className="mono">{requirement.id}</strong>
        {requirementBadge(route)}
      </div>
      <p style={{ margin: "0.3rem 0", fontSize: "0.86rem" }}>{requirement.discriminating_question}</p>
      <div className="badges">
        {(requirement.answer_classes ?? []).map((c) => (
          <span key={c} className="badge neutral">
            {c}
          </span>
        ))}
      </div>
      {route.refusal && <p className="reason-text">No acquisition route: {route.refusal}</p>}
      {requirement.unresolvable && <p className="reason-text">{requirement.unresolvable_reason}</p>}

      {route.route && !anyInFlight && (
        <div className="section-gap">
          <p className="reason-text" style={{ margin: "0 0 0.3rem 0" }}>
            Route: {route.route.source_id} under {route.route.mandate_id} (rev {route.route.mandate_revision}) — discriminates{" "}
            {route.route.hypothesis_ids.join(", ")}.
          </p>
          <textarea style={fieldStyle} rows={2} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
          {overview.sam_enabled && (
            <label className="reason-text" style={{ display: "flex", gap: "0.4rem", alignItems: "center", marginTop: 4 }}>
              <input type="checkbox" checked={useSam} onChange={(e) => setUseSam(e.target.checked)} />
              derive regions with SAM 3.1 (billed, ≤ {usd(2500)} per image)
            </label>
          )}
          {useSam && (
            <input style={{ ...fieldStyle, marginTop: 4 }} value={samPrompt} onChange={(e) => setSamPrompt(e.target.value)} />
          )}
          <div className="action-row">
            <button
              className="button-secondary"
              disabled={busy || !token || !instructions.trim()}
              onClick={() =>
                run(() => acquisitionApi.propose(caseId, requirement.id, token, instructions, useSam ? samPrompt : null))
              }
            >
              Propose capture
            </button>
          </div>
        </div>
      )}

      {pendingProposals.map((p) => (
        <div key={p.id} className="recovery-card">
          <h3>Proposal awaiting a human decision</h3>
          <p className="reason-text" style={{ margin: 0 }}>
            digest {p.proposal_digest.slice(0, 16)}… · proposed by {p.proposed_by} · source {p.proposal.source_id} · data
            goes to <span className="mono">{p.proposal.retention.destination}</span> · processing:{" "}
            {p.proposal.processing_plan ? `SAM “${p.proposal.processing_plan.prompt}”` : "none"} · cost ceiling{" "}
            {usd(p.proposal.source_usage_ceiling.usd_micros + (p.proposal.processing_plan?.usage_ceiling.usd_micros ?? 0))}
          </p>
          <div className="action-row">
            <button className="button-primary" disabled={busy || !token} onClick={() => run(() => acquisitionApi.authorize(caseId, p.id, token))}>
              Authorize exactly this (single use, 15 min)
            </button>
          </div>
        </div>
      ))}

      {usableGrants.map((a) => (
        <div key={a.id} className="recovery-card">
          <h3>Authorized — take the photograph and submit it</h3>
          <p className="reason-text" style={{ margin: "0 0 0.3rem 0" }}>
            {a.authorization.authorizer_identity} · expires {new Date(a.authorization.expires_at).toLocaleTimeString()} · only
            the authorizing operator's token can dispatch it
          </p>
          <input type="file" accept="image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <div className="action-row">
            <button
              className="button-primary"
              disabled={busy || !token || !file}
              onClick={() => file && run(() => acquisitionApi.capture(caseId, a.id, token, file))}
            >
              Submit capture
            </button>
          </div>
        </div>
      ))}

      {history.map((h) => (
        <HistoryItem key={h.workflow.workflow_id} caseId={caseId} record={h} route={route} busy={busy} run={run} token={token} />
      ))}

      {open && history.length > 0 && !anyInFlight && (
        <div className="section-gap">
          <input
            style={fieldStyle}
            value={abstainReason}
            onChange={(e) => setAbstainReason(e.target.value)}
            placeholder="Why this evidence is no longer obtainable"
          />
          <div className="action-row">
            <button
              className="button-secondary"
              disabled={busy || !token || !abstainReason.trim()}
              onClick={() =>
                run(() => acquisitionApi.abstain(caseId, requirement.id, token, route.requirement_revision, abstainReason))
              }
            >
              Close honestly as unresolvable
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function AcquisitionPanel({
  caseId,
  caseVersion,
  onChanged,
  token,
  onTokenChange,
}: {
  caseId: string;
  token: string;
  onTokenChange: (token: string) => void;
  // Changes whenever the case's activity log does (including a dev
  // reset), so this panel re-reads instead of showing stale grants.
  caseVersion: number;
  onChanged: () => Promise<void>;
}) {
  const [overview, setOverview] = useState<AcquisitionOverview | null>(null);
  const [loadedAtMs, setLoadedAtMs] = useState(0);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const reload = () =>
    acquisitionApi.overview(caseId).then((o) => {
      setOverview(o);
      setLoadedAtMs(Date.now());
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

  if (!overview) return null;

  return (
    <section className="panel">
      <h2>Acquisition</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        New evidence only through a stated question, a human authorization, and an identified evaluator. A capture or a SAM
        region never resolves anything by itself.
      </p>
      {!overview.enabled ? (
        <p className="reason-text">
          Disabled in this deployment — set <span className="mono">KRAKADYL_OPERATOR_TOKENS</span> (see{" "}
          <span className="mono">tools/operator_token.py</span>).
        </p>
      ) : (
        <input
          type="password"
          style={fieldStyle}
          value={token}
          onChange={(e) => onTokenChange(e.target.value)}
          placeholder="Operator token (kept in this tab only)"
          autoComplete="off"
        />
      )}
      {localError && <p className="reason-text" style={{ color: "#ff9d96" }}>{localError}</p>}
      {overview.routes.map((route) => (
        <RequirementCard
          key={route.requirement.id}
          caseId={caseId}
          route={route}
          overview={overview}
          busy={busy}
          run={run}
          token={token}
          loadedAtMs={loadedAtMs}
        />
      ))}
    </section>
  );
}
