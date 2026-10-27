import type { components, paths } from "./api-generated";

// Regenerate named API schemas with `npm run gen:api-types` while the
// backend serves its OpenAPI document. Activity events and execution
// manifests are refined below because FastAPI currently exposes those
// two endpoint-local shapes only as generic dictionaries.

// Port 8000 is the FastAPI/uvicorn default; this project's own dev
// instructions (frontend/README.md) run it there. If something else on
// your machine already holds 8000, start uvicorn on another port and
// override this at build time instead of hand-editing it here.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

type Schemas = components["schemas"];

export type EvidenceCustody = Schemas["EvidenceCustody"];
export type Observation = Schemas["Observation"];
export type EvidenceItem = Schemas["EvidenceItem"];
export type Hypothesis = Schemas["Hypothesis"];
export type HypothesisItem = Schemas["HypothesisItem"];
export type Mission = Schemas["Mission"];
export type Mandate = Schemas["Mandate"];
export type ExclusionRecord = Schemas["ExclusionRecord"];
export type PreparedAction = Schemas["PreparedAction"];
export type Decision = Schemas["Decision"];
export type Receipt = Schemas["Receipt"];
export type CaseOverview = Schemas["CaseOverview"];
export type PrepareResponse = Schemas["PrepareResponse"];
export type RecoverResponse = Schemas["RecoverResponse"];
export type MuseProposeResponse = Schemas["MuseProposeResponse"];
export type LayaSignals = Schemas["AnalyzeNoteResponse"];

type GeneratedActivity =
  paths["/api/cases/{case_id}/activity"]["get"]["responses"][200]["content"]["application/json"];

export type ActivityEvent = GeneratedActivity[number] & {
  ts: string;
  kind: string;
  summary: string;
  detail: Record<string, unknown>;
};

type GeneratedExecuteResponse = Schemas["ExecuteResponse"];
type GeneratedManifest = NonNullable<GeneratedExecuteResponse["manifest"]>;

export type ExecuteResponse = Omit<GeneratedExecuteResponse, "manifest"> & {
  manifest:
    | (GeneratedManifest & {
        excluded_resources: ExclusionRecord[];
      })
    | null;
};

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

// Hardcoded because there is no login/session system yet — this is a
// single-investigator local demo. Found by red-team review: the API
// didn't check identity against Mandate.principal AT ALL; it now does,
// at every action endpoint. This constant is the caller-ASSERTED
// identity, not a cryptographic one — a real deployment replaces this
// with whatever the actual login session resolves to, not a literal.
const ACTING_PRINCIPAL = "investigator-A";

export const api = {
  getCase: (caseId: string) => request<CaseOverview>(`/api/cases/${caseId}`),
  getActivity: (caseId: string) => request<ActivityEvent[]>(`/api/cases/${caseId}/activity`),
  prepare: (caseId: string) =>
    request<PrepareResponse>(`/api/cases/${caseId}/actions/prepare`, {
      method: "POST",
      body: JSON.stringify({ principal: ACTING_PRINCIPAL }),
    }),
  proposeWithMuse: (caseId: string) =>
    request<MuseProposeResponse>(`/api/cases/${caseId}/actions/propose-with-muse`, {
      method: "POST",
      body: JSON.stringify({ principal: ACTING_PRINCIPAL }),
    }),
  analyzeNote: (caseId: string, noteText: string) =>
    request<LayaSignals>(`/api/cases/${caseId}/analyze-note`, {
      method: "POST",
      body: JSON.stringify({ principal: ACTING_PRINCIPAL, note_text: noteText }),
    }),
  execute: (caseId: string, preparedActionId: string) =>
    request<ExecuteResponse>(`/api/cases/${caseId}/actions/execute`, {
      method: "POST",
      body: JSON.stringify({ principal: ACTING_PRINCIPAL, prepared_action_id: preparedActionId }),
    }),
  recover: (caseId: string) =>
    request<RecoverResponse>(`/api/cases/${caseId}/actions/recover`, {
      method: "POST",
      body: JSON.stringify({ principal: ACTING_PRINCIPAL }),
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
