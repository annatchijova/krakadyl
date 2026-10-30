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
export type AcquisitionOverview = Schemas["AcquisitionOverview"];
export type RouteView = Schemas["RouteView"];
export type StoredAcquisitionProposal = Schemas["StoredAcquisitionProposal"];
export type StoredAcquisitionAuthorization = Schemas["StoredAcquisitionAuthorization"];
export type AcquisitionRecordView = Schemas["AcquisitionRecordView"];
export type AnnotationView = Schemas["AnnotationView"];
export type EvaluationOutcome = Schemas["EvaluationOutcome"];
export type EvidenceRequirement = Schemas["EvidenceRequirement"];
export type TeamOverview = Schemas["TeamOverview"];
export type TeamRequirementView = Schemas["TeamRequirementView"];
export type TeamRecord = Schemas["TeamRecord"];
export type Conflict = Schemas["Conflict"];
export type ClaimKind = Schemas["ClaimKind"];
export type HandoffView = Schemas["HandoffView"];
export type HandoffItem = Schemas["HandoffItem"];
export type EvidenceRefInput = Schemas["EvidenceRef"];
export type CounterfactualView = Schemas["CounterfactualView"];
export type DeltaInput = Schemas["Delta"];
export type DeltaKind = Schemas["DeltaKind"];
export type CounterfactualOutcome = Schemas["Outcome"];

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

// Level 3 acquisition endpoints do NOT use ACTING_PRINCIPAL: identity is
// the operator bearer token the request proves. The token lives only in
// React state for the tab's lifetime — never in localStorage.
function bearer(token: string): Record<string, string> {
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

export const acquisitionApi = {
  overview: (caseId: string) => request<AcquisitionOverview>(`/api/cases/${caseId}/acquisition`),
  propose: (caseId: string, requirementId: string, token: string, captureInstructions: string, samPrompt: string | null) =>
    request<StoredAcquisitionProposal>(`/api/cases/${caseId}/requirements/${requirementId}/acquisition-proposals`, {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify({ capture_instructions: captureInstructions, sam_prompt: samPrompt }),
    }),
  authorize: (caseId: string, proposalId: string, token: string) =>
    request<StoredAcquisitionAuthorization>(`/api/cases/${caseId}/acquisition-proposals/${proposalId}/authorize`, {
      method: "POST",
      headers: bearer(token),
    }),
  capture: (caseId: string, authorizationId: string, token: string, file: File) =>
    request<AcquisitionRecordView>(`/api/cases/${caseId}/acquisition-authorizations/${authorizationId}/capture`, {
      method: "POST",
      headers: { "Content-Type": file.type, Authorization: `Bearer ${token}` },
      body: file,
    }),
  // Captured bytes need the operator token, which an <img src> cannot
  // send — fetched as a blob instead; the caller revokes the object URL.
  observationObjectUrl: async (caseId: string, workflowId: string, token: string) => {
    const path = `/api/cases/${caseId}/acquisitions/${workflowId}/observation`;
    const resp = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!resp.ok) throw new Error(`GET ${path} -> ${resp.status}: ${await resp.text()}`);
    return URL.createObjectURL(await resp.blob());
  },
  annotation: (caseId: string, workflowId: string, token: string) =>
    request<AnnotationView>(`/api/cases/${caseId}/acquisitions/${workflowId}/annotation`, { headers: bearer(token) }),
  evaluate: (
    caseId: string,
    workflowId: string,
    token: string,
    body: { expected_requirement_revision: string; criterion_id: string; criterion_version: string; outcome: EvaluationOutcome; rationale: string },
  ) =>
    request<AcquisitionRecordView>(`/api/cases/${caseId}/acquisitions/${workflowId}/evaluations`, {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify(body),
    }),
  abstain: (caseId: string, requirementId: string, token: string, expectedRevision: string, reason: string) =>
    request<EvidenceRequirement>(`/api/cases/${caseId}/requirements/${requirementId}/abstain`, {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify({ expected_requirement_revision: expectedRevision, reason }),
    }),
  reconcile: (caseId: string, attemptId: string, token: string, disposition: "confirmed_not_dispatched" | "accepted_as_unknown", rationale: string) =>
    request<AcquisitionRecordView>(`/api/cases/${caseId}/acquisition-attempts/${attemptId}/reconcile`, {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify({ disposition, rationale }),
    }),
};

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
  // Needs the operator token once acquisition is enabled: reset also
  // deletes acquisition records.
  devReset: (caseId: string, token: string) =>
    request<{ ok: boolean }>(`/api/dev/cases/${caseId}/reset`, {
      method: "POST",
      headers: token ? bearer(token) : { "Content-Type": "application/json" },
    }),
};

export type TeamStatement = {
  kind: ClaimKind;
  statement: string;
  expected_requirement_revision: string;
  evidence_refs?: EvidenceRefInput[];
  refers_to?: string[];
  verification_method?: string | null;
  resolves_conflict_id?: string | null;
  decision?: "keep_current_state" | "reopen_requirement" | null;
};

// Level 4: every statement and handoff is attributed to the operator
// token the request proves, never to a name in the body.
export const teamApi = {
  overview: (caseId: string) => request<TeamOverview>(`/api/cases/${caseId}/team`),
  say: (caseId: string, requirementId: string, token: string, body: TeamStatement) =>
    request<TeamOverview>(`/api/cases/${caseId}/requirements/${requirementId}/team-records`, {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify(body),
    }),
  handoff: (caseId: string) => request<HandoffView>(`/api/cases/${caseId}/handoff`),
  handOver: (
    caseId: string,
    token: string,
    body: { to_actor: string; seen_state_digest: string; transfer_requirement_ids: string[]; note: string },
  ) =>
    request<HandoffView>(`/api/cases/${caseId}/handoffs`, {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify(body),
    }),
  accept: (caseId: string, handoffId: string, token: string) =>
    request<HandoffView>(`/api/cases/${caseId}/handoffs/${handoffId}/accept`, {
      method: "POST",
      headers: bearer(token),
    }),
};

// Level 5: hypotheticals only. Nothing here can change the case or
// produce anything the execute endpoint accepts.
export const counterfactualApi = {
  list: (caseId: string) => request<CounterfactualView[]>(`/api/cases/${caseId}/counterfactuals`),
  evaluate: (
    caseId: string,
    token: string,
    body: { question: { allowed_device: string; destination: string }; deltas: DeltaInput[] },
  ) =>
    request<CounterfactualView>(`/api/cases/${caseId}/counterfactuals`, {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify(body),
    }),
};
