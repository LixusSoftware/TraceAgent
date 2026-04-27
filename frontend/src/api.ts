import type {
  Artifact,
  AuditReport,
  DashboardResponse,
  EventItem,
  ExplanationResponse,
  FinishRunResponse,
  GraphResponse,
  RunCreatePayload,
  RunCreateResponse,
  RunAnalytics,
  RunCompareResponse,
  RunFilters,
  SimilarRunFilters,
  TurnCreatePayload,
  TurnCreateResponse,
  TurnOut,
  RunListItem,
  RunOverview,
  TimelineResponse
} from "./types";


const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) {
        detail = `Request failed: ${response.status} (${body.detail})`;
      }
    } catch {
      // Preserve generic error for non-json responses.
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  listRuns: (filters?: RunFilters) => {
    const params = new URLSearchParams();
    if (filters?.limit !== undefined) params.set("limit", String(filters.limit));
    if (filters?.offset !== undefined) params.set("offset", String(filters.offset));
    if (filters?.agent_name) params.set("agent_name", filters.agent_name);
    if (filters?.status) params.set("status", filters.status);
    if (filters?.provider) params.set("provider", filters.provider);
    if (filters?.model) params.set("model", filters.model);
    if (filters?.search) params.set("search", filters.search);
    if (filters?.started_after) params.set("started_after", filters.started_after);
    if (filters?.started_before) params.set("started_before", filters.started_before);
    const query = params.toString();
    return requestJson<RunListItem[]>(`/api/runs${query ? `?${query}` : ""}`);
  },
  createRun: (payload: RunCreatePayload) =>
    requestJson<RunCreateResponse>("/api/runs", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  createTurn: (runId: string, payload: TurnCreatePayload) =>
    requestJson<TurnCreateResponse>(`/api/runs/${runId}/turns`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  finishRun: (runId: string, finalOutput: unknown) =>
    requestJson<FinishRunResponse>(`/api/runs/${runId}/finish`, {
      method: "POST",
      body: JSON.stringify({ final_output: finalOutput, artifacts: [] })
    }),
  getRun: (id: string) => requestJson<RunOverview>(`/api/runs/${id}`),
  getTimeline: (id: string) => requestJson<TimelineResponse>(`/api/runs/${id}/timeline`),
  getGraph: (id: string, view: "execution" | "decisions") =>
    requestJson<GraphResponse>(`/api/runs/${id}/graph?view=${view}`),
  getAnalytics: (id: string, filters: SimilarRunFilters) => {
    const params = new URLSearchParams({
      same_agent_only: String(filters.sameAgentOnly),
      status: filters.status === "all" ? "" : filters.status,
      shared_tools_only: String(filters.sharedToolsOnly),
      min_score: String(filters.minScore),
      limit: String(filters.limit)
    });
    if (filters.status === "all") {
      params.delete("status");
    }
    return requestJson<RunAnalytics>(`/api/runs/${id}/analytics?${params.toString()}`);
  },
  compareRuns: (leftRunId: string, rightRunId: string) =>
    requestJson<RunCompareResponse>(`/api/runs/compare?left_run_id=${leftRunId}&right_run_id=${rightRunId}`),
  getExplanation: (id: string) => requestJson<ExplanationResponse>(`/api/runs/${id}/explanation`),
  getArtifacts: (id: string) => requestJson<Artifact[]>(`/api/runs/${id}/artifacts`),
  getAudit: (id: string) => requestJson<AuditReport>(`/api/runs/${id}/audit`),
  getDashboard: (period: "24h" | "7d" | "30d" = "24h") =>
    requestJson<DashboardResponse>(`/api/dashboard?period=${period}`),
  getRunEvents: (runId: string, params?: { type?: string; status?: string; actor?: string; tool_name?: string; step_id?: string; limit?: number; offset?: number }) => {
    const search = new URLSearchParams();
    if (params?.type) search.set("type", params.type);
    if (params?.status) search.set("status", params.status);
    if (params?.actor) search.set("actor", params.actor);
    if (params?.tool_name) search.set("tool_name", params.tool_name);
    if (params?.step_id) search.set("step_id", params.step_id);
    if (params?.limit !== undefined) search.set("limit", String(params.limit));
    if (params?.offset !== undefined) search.set("offset", String(params.offset));
    const query = search.toString();
    return requestJson<EventItem[]>(`/api/runs/${runId}/events${query ? `?${query}` : ""}`);
  },
  getRunTurns: (runId: string) => requestJson<TurnOut[]>(`/api/runs/${runId}/turns`),
};
