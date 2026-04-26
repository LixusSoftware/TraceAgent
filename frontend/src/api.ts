import type {
  Artifact,
  AuditReport,
  ExplanationResponse,
  FinishRunResponse,
  GraphResponse,
  RunCreatePayload,
  RunCreateResponse,
  RunAnalytics,
  RunCompareResponse,
  SimilarRunFilters,
  TurnCreatePayload,
  TurnCreateResponse,
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
  listRuns: () => requestJson<RunListItem[]>("/api/runs"),
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
  getAudit: (id: string) => requestJson<AuditReport>(`/api/runs/${id}/audit`)
};

