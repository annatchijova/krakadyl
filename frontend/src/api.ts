// Hand-written to mirror krakadyl/api/app.py's response models exactly.
// Not code-generated from the Python schema yet — docs/language-decision.md
// names that as the eventual approach ("TypeScript types are generated
// from the Python schema, never hand-duplicated"); this is the honest
// interim state, not a claim that generation already happens. Keep this
// file in lockstep with app.py's Pydantic models by hand until it does.

// Port 8000 is the FastAPI/uvicorn default; this project's own dev
// instructions (frontend/README.md) run it there. If something else on
// your machine already holds 8000, start uvicorn on another port and
// override this at build time instead of hand-editing it here.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface EvidenceCustody {
  acquired_by: string;
  acquired_at: string;
  acquisition_method: string;
  possessors: unknown[];
  transformations: unknown[];
  integrity_digest: string | null;
  integrity_verified: boolean;
  integrity_verified_by: string | null;
}

export interface Observation {
  id: string;
  source: string;
  digest: string;
  captured_at: string;
  event_time: string | null;
  actor: string;
  visual_region: string | null;
  evidence_custody: EvidenceCustody;
}

export interface EvidenceItem {
  observation: Observation;
  in_mandate_scope: boolean;
  integrity_ok: boolean;
  requirement_id: string | null;
  requirement_status: string | null;
  independently_verified: boolean;
}

export interface Hypothesis {
  id: string;
  explanation: string;
  status: "proposed" | "accepted" | "rejected";
  supporting_claim_ids: string[];
  contradicting_claim_ids: string[];
  discriminating_requirement_id: string | null;
}

export interface HypothesisItem {
  hypothesis: Hypothesis;
  needs_review: boolean;
  review_reason: string | null;
}

export interface Mission {
  id: string;
  objective: string;
  domain: string;
  mandate_id: string;
  termination_criteria: string;
  created_at: string;
}

export interface Mandate {
  id: string;
  issuer: string;
  principal: string;
  resources: string[];
  operations: string[];
  destinations: string[];
  valid_from: string;
  valid_until: string | null;
  revoked: boolean;
  revoked_reason: string | null;
  revision: string;
}

export interface ExclusionRecord {
  resource_id: string;
  reason: string;
}

export interface PreparedAction {
  id: string;
  proposed_action_id: string;
  payload_digest: string;
  resource: string;
  operation: string;
  destination: string;
  resources_touched: string[];
  excluded_sources: string[];
  excluded_resource_reasons: ExclusionRecord[];
  source_revision_checked: string;
  mandate_revision_checked: string;
  expires_at: string;
  nonce: string;
}

export interface Decision {
  id: string;
  proposed_action_id: string;
  verdict: "allowed" | "confirm" | "gather_evidence" | "forbidden";
  evidence_state: string;
  authority_state: string;
  reasons: string[];
  supporting_refs: string[];
  decided_at: string;
}

export interface Receipt {
  id: string;
  proposed_action_id: string;
  decision_id: string;
  executed: boolean;
  observed_effect: string | null;
  uncertain_outcome: boolean;
  prev_hash: string | null;
  hash: string;
  created_at: string;
}

export interface CaseOverview {
  mission: Mission;
  mandate: Mandate;
  evidence: EvidenceItem[];
  hypotheses: HypothesisItem[];
  latest_prepared_action: PreparedAction | null;
  latest_decision: Decision | null;
}

export interface ActivityEvent {
  ts: string;
  kind: string;
  summary: string;
  detail: Record<string, unknown>;
}

export interface PrepareResponse {
  decision: Decision;
  prepared: PreparedAction | null;
}

export interface ExecuteResponse {
  receipt: Receipt;
  manifest: {
    device: string | null;
    destination: string;
    excluded_devices: string[];
    excluded_resources: ExclusionRecord[];
    included: unknown[];
  } | null;
}

export interface RecoverResponse {
  attempted: boolean;
  excluded_resources: string[];
  decision: Decision | null;
  prepared: PreparedAction | null;
  closed_reason: string | null;
}

export interface MuseProposeResponse {
  muse_operation: string;
  muse_allowed_device: string;
  muse_destination: string;
  muse_reasoning: string;
  decision: Decision;
  prepared: PreparedAction | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${init?.method ?? "GET"} ${path} -> ${resp.status}: ${body}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  getCase: (caseId: string) => request<CaseOverview>(`/api/cases/${caseId}`),
  getActivity: (caseId: string) => request<ActivityEvent[]>(`/api/cases/${caseId}/activity`),
  prepare: (caseId: string) =>
    request<PrepareResponse>(`/api/cases/${caseId}/actions/prepare`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  proposeWithMuse: (caseId: string) =>
    request<MuseProposeResponse>(`/api/cases/${caseId}/actions/propose-with-muse`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  execute: (caseId: string, preparedActionId: string) =>
    request<ExecuteResponse>(`/api/cases/${caseId}/actions/execute`, {
      method: "POST",
      body: JSON.stringify({ prepared_action_id: preparedActionId }),
    }),
  recover: (caseId: string) =>
    request<RecoverResponse>(`/api/cases/${caseId}/actions/recover`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  devTamper: (caseId: string, observationId: string) =>
    request<{ ok: boolean }>(`/api/dev/cases/${caseId}/tamper`, {
      method: "POST",
      body: JSON.stringify({ observation_id: observationId }),
    }),
  devRevokeMandate: (caseId: string) =>
    request<{ ok: boolean }>(`/api/dev/cases/${caseId}/revoke-mandate`, {
      method: "POST",
      body: JSON.stringify({ reason: "case reassigned to another unit" }),
    }),
  devUnresolveHypothesisRequirement: (caseId: string) =>
    request<{ ok: boolean }>(`/api/dev/cases/${caseId}/unresolve-hypothesis-requirement`, {
      method: "POST",
    }),
  devReset: (caseId: string) =>
    request<{ ok: boolean }>(`/api/dev/cases/${caseId}/reset`, { method: "POST" }),
};
