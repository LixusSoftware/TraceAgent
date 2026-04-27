import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { api } from "./api";
import { AuditDashboard } from "./components/AuditDashboard";
import { CompareWorkspace } from "./components/CompareWorkspace";
import { DashboardView } from "./components/DashboardView";
import { InspectorPanel } from "./components/InspectorPanel";
import { RunWorkspace } from "./components/RunWorkspace";
import { useEventStream } from "./hooks/useEventStream";
import type {
  AuditReport,
  Artifact,
  DashboardResponse,
  EventItem,
  ExplanationResponse,
  GraphResponse,
  RunAnalytics,
  RunCompareResponse,
  RunFilters,
  RunListItem,
  RunOverview,
  SimilarRunFilters,
  TimelineResponse
} from "./types";
import { buildFlow, defaultSimilarRunFilters, formatDuration } from "./view-utils";

type ViewMode = "execution" | "decisions";
type WorkspaceMode = "run" | "compare" | "dashboard";

type LaunchFormState = {
  agentName: string;
  goal: string;
  model: string;
  provider: string;
  systemPrompt: string;
  userPrompt: string;
};

const INITIAL_LAUNCH_FORM: LaunchFormState = {
  agentName: "lmstudio-local-agent",
  goal: "",
  model: "google/gemma-4-e4b",
  provider: "openai",
  systemPrompt: "",
  userPrompt: ""
};

function toErrorMessage(reason: unknown): string {
  if (reason instanceof Error) {
    return reason.message;
  }
  return "Unexpected error while calling the API.";
}

export default function App() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runSearch, setRunSearch] = useState("");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("run");
  const [activeTerminalTab, setActiveTerminalTab] = useState<"console" | "auditing" | "output">("console");
  const [view, setView] = useState<ViewMode>("execution");
  const [overview, setOverview] = useState<RunOverview | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [analytics, setAnalytics] = useState<RunAnalytics | null>(null);
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [audit, setAudit] = useState<AuditReport | null>(null);
  const [isAuditLoading, setIsAuditLoading] = useState(false);
  const [selectedEvidenceIds, setSelectedEvidenceIds] = useState<number[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [similarFilters, setSimilarFilters] = useState<SimilarRunFilters>(defaultSimilarRunFilters);
  const [comparedRunId, setComparedRunId] = useState<string | null>(null);
  const [compareData, setCompareData] = useState<RunCompareResponse | null>(null);
  const [compareSelection, setCompareSelection] = useState<{ left: number[]; right: number[] }>({ left: [], right: [] });
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [isDashboardLoading, setIsDashboardLoading] = useState(false);
  const [runFilters, setRunFilters] = useState<RunFilters>({});
  const [error, setError] = useState<string | null>(null);
  const [launchForm, setLaunchForm] = useState<LaunchFormState>(INITIAL_LAUNCH_FORM);
  const [launchNotice, setLaunchNotice] = useState<string | null>(null);
  const [isLaunchingRun, setIsLaunchingRun] = useState(false);
  const [isRefreshingRuns, setIsRefreshingRuns] = useState(false);
  const [isRunDataLoading, setIsRunDataLoading] = useState(false);
  const [isAnalyticsLoading, setIsAnalyticsLoading] = useState(false);
  const [isCompareLoading, setIsCompareLoading] = useState(false);

  const refreshRuns = useCallback(async (preferredRunId?: string) => {
    setIsRefreshingRuns(true);
    try {
      const data = await api.listRuns(runFilters);
      setRuns(data);
      setSelectedRunId((current) => {
        if (preferredRunId && data.some((run) => run.id === preferredRunId)) {
          return preferredRunId;
        }
        if (current && data.some((run) => run.id === current)) {
          return current;
        }
        return data[0]?.id ?? null;
      });
    } finally {
      setIsRefreshingRuns(false);
    }
  }, [runFilters]);

  const updateLaunchField = <K extends keyof LaunchFormState>(field: K, value: LaunchFormState[K]) => {
    setLaunchForm((current) => ({ ...current, [field]: value }));
  };

  const resetEvidenceSelection = () => {
    setSelectedEvidenceIds([]);
    setSelectedEventId(null);
  };

  const resetCompareSelection = () => {
    setCompareSelection({ left: [], right: [] });
  };

  const handleLaunchRun = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const agentName = launchForm.agentName.trim();
    const model = launchForm.model.trim();
    const userPrompt = launchForm.userPrompt.trim();
    const systemPrompt = launchForm.systemPrompt.trim();

    if (!agentName || !model || !userPrompt) {
      setError("Agent name, model and user prompt are required to launch a run.");
      return;
    }

    setError(null);
    setLaunchNotice(null);
    setIsLaunchingRun(true);
    try {
      const goal = launchForm.goal.trim() || `Live prompt: ${userPrompt.slice(0, 96)}`;
      const run = await api.createRun({
        agent_name: agentName,
        goal,
        metadata: {
          source: "frontend-launcher",
          provider: launchForm.provider,
          model
        }
      });

      const messages: Array<{ role: string; content: string }> = [];
      if (systemPrompt) {
        messages.push({ role: "system", content: systemPrompt });
      }
      messages.push({ role: "user", content: userPrompt });

      const turn = await api.createTurn(run.run_id, {
        provider: launchForm.provider,
        model,
        messages,
        tools: [],
        tool_choice: "auto"
      });

      if (turn.status === "message") {
        await api.finishRun(run.run_id, turn.assistant_message ?? { role: "assistant", content: "" });
        setLaunchNotice("Run created and completed. It is now visible in the run list.");
      } else {
        setLaunchNotice("Run created, but the model requested tools. The run stays in running state until tool results are submitted.");
      }

      await refreshRuns(run.run_id);
      setWorkspaceMode("run");
      setComparedRunId(null);
      resetCompareSelection();
      resetEvidenceSelection();
    } catch (reason) {
      setError(toErrorMessage(reason));
    } finally {
      setIsLaunchingRun(false);
    }
  };

  useEffect(() => {
    refreshRuns().catch((reason) => setError(toErrorMessage(reason)));
  }, [refreshRuns]);

  // ── Feature 1: Auto-refresh ───────────────────────────────────────────────
  // Poll run list every 30 s so sidebar stays up to date.
  useEffect(() => {
    const id = setInterval(() => {
      refreshRuns().catch(() => undefined);
    }, 30_000);
    return () => clearInterval(id);
  }, [refreshRuns]);

  // SSE live stream for active run
  useEventStream(selectedRunId, useCallback((evt) => {
    if (evt.type === "event") {
      // Refresh run data when new events arrive
      if (selectedRunId) {
        Promise.all([
          api.getRun(selectedRunId),
          api.getTimeline(selectedRunId),
        ])
          .then(([runOverview, timelineResponse]) => {
            setOverview(runOverview);
            setTimeline(timelineResponse);
          })
          .catch(() => undefined);
      }
    }
  }, [selectedRunId]));


  useEffect(() => {
    if (!selectedRunId) {
      setOverview(null);
      setTimeline(null);
      setGraph(null);
      setExplanation(null);
      setArtifacts([]);
      setIsRunDataLoading(false);
      return;
    }

    let isCurrent = true;
    setError(null);
    setIsRunDataLoading(true);
    setAudit(null);
    Promise.all([
      api.getRun(selectedRunId),
      api.getTimeline(selectedRunId),
      api.getGraph(selectedRunId, view),
      api.getExplanation(selectedRunId),
      api.getArtifacts(selectedRunId)
    ])
      .then(([runOverview, timelineResponse, graphResponse, explanationResponse, artifactResponse]) => {
        if (!isCurrent) {
          return;
        }
        setOverview(runOverview);
        setTimeline(timelineResponse);
        setGraph(graphResponse);
        setExplanation(explanationResponse);
        setArtifacts(artifactResponse);
      })
      .catch((reason) => {
        if (isCurrent) {
          setError(toErrorMessage(reason));
        }
      })
      .finally(() => {
        if (isCurrent) {
          setIsRunDataLoading(false);
        }
      });

    // Fetch audit report separately so it doesn't block main data
    setIsAuditLoading(true);
    api
      .getAudit(selectedRunId)
      .then((auditResponse) => {
        if (isCurrent) {
          setAudit(auditResponse);
        }
      })
      .catch(() => {
        // Non-critical – audit panel will show empty state
      })
      .finally(() => {
        if (isCurrent) {
          setIsAuditLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedRunId, view]);

  useEffect(() => {
    if (!selectedRunId) {
      setAnalytics(null);
      setIsAnalyticsLoading(false);
      return;
    }

    let isCurrent = true;
    setError(null);
    setIsAnalyticsLoading(true);
    api
      .getAnalytics(selectedRunId, similarFilters)
      .then((analyticsResponse) => {
        if (isCurrent) {
          setAnalytics(analyticsResponse);
        }
      })
      .catch((reason) => {
        if (isCurrent) {
          setError(toErrorMessage(reason));
        }
      })
      .finally(() => {
        if (isCurrent) {
          setIsAnalyticsLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedRunId, similarFilters]);

  // Load dashboard data
  useEffect(() => {
    if (workspaceMode !== "dashboard") {
      setDashboard(null);
      setIsDashboardLoading(false);
      return;
    }
    let isCurrent = true;
    setIsDashboardLoading(true);
    api.getDashboard("24h")
      .then((data) => {
        if (isCurrent) setDashboard(data);
      })
      .catch((reason) => {
        if (isCurrent) setError(toErrorMessage(reason));
      })
      .finally(() => {
        if (isCurrent) setIsDashboardLoading(false);
      });
    return () => { isCurrent = false; };
  }, [workspaceMode]);

  useEffect(() => {
    if (workspaceMode !== "compare" || !selectedRunId) {
      return;
    }

    if (comparedRunId && comparedRunId !== selectedRunId) {
      return;
    }

    const fallbackRunId = runs.find((run) => run.id !== selectedRunId)?.id ?? null;
    setComparedRunId(fallbackRunId);
  }, [workspaceMode, selectedRunId, comparedRunId, runs]);

  useEffect(() => {
    if (workspaceMode !== "compare" || !selectedRunId || !comparedRunId || comparedRunId === selectedRunId) {
      setCompareData(null);
      resetCompareSelection();
      setIsCompareLoading(false);
      return;
    }

    let isCurrent = true;
    setError(null);
    setIsCompareLoading(true);
    api
      .compareRuns(selectedRunId, comparedRunId)
      .then((response) => {
        if (isCurrent) {
          setCompareData(response);
        }
      })
      .catch((reason) => {
        if (isCurrent) {
          setError(toErrorMessage(reason));
        }
      })
      .finally(() => {
        if (isCurrent) {
          setIsCompareLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [workspaceMode, selectedRunId, comparedRunId]);

  const evidenceLookup = explanation?.evidence ?? {};
  const selectedEvents = (selectedEvidenceIds.length > 0 ? selectedEvidenceIds : selectedEventId ? [selectedEventId] : [])
    .map((eventId) => evidenceLookup[String(eventId)])
    .filter((event): event is EventItem => Boolean(event));
  const selectedPrimaryEvent = selectedEvents[0] ?? null;
  const compareLeftEvents = compareSelection.left
    .map((eventId) => compareData?.evidence.left[String(eventId)])
    .filter((event): event is EventItem => Boolean(event));
  const compareRightEvents = compareSelection.right
    .map((eventId) => compareData?.evidence.right[String(eventId)])
    .filter((event): event is EventItem => Boolean(event));
  const comparePrimaryLeftEvent = compareLeftEvents[0] ?? null;
  const comparePrimaryRightEvent = compareRightEvents[0] ?? null;

  const mainFlow = useMemo(() => buildFlow(graph, "main"), [graph]);
  const toolFlow = useMemo(() => buildFlow(analytics?.tool_graph ?? null, "tool"), [analytics]);
  const maxToolDuration = useMemo(
    () => Math.max(1, ...(analytics?.tool_metrics.map((metric) => metric.total_duration_ms) ?? [1])),
    [analytics]
  );
  const hasComparableRuns = useMemo(() => runs.some((run) => run.id !== selectedRunId), [runs, selectedRunId]);
  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId) ?? null, [runs, selectedRunId]);
  const filteredRuns = useMemo(() => {
    const query = runSearch.trim().toLowerCase();
    if (!query) {
      return runs;
    }

    return runs.filter((run) =>
      [run.agent_name, run.goal, run.status, run.provider ?? "", run.model ?? "", run.id].join(" ").toLowerCase().includes(query)
    );
  }, [runs, runSearch]);
  const isAnyBusy = isLaunchingRun || isRefreshingRuns || isRunDataLoading || isAnalyticsLoading || isCompareLoading;

  // ── Feature 3: Aggregate stats ────────────────────────────────────────────
  const globalStats = useMemo(() => {
    if (runs.length === 0) return null;
    const completed = runs.filter((r) => r.status === "completed").length;
    const failed = runs.filter((r) => r.status === "failed").length;
    const totalErrors = runs.reduce((s, r) => s + r.error_count, 0);
    const totalTokens = 0; // available per-run in analytics, not in list
    return { total: runs.length, completed, failed, totalErrors, totalTokens, pct: Math.round((completed / runs.length) * 100) };
  }, [runs]);

  const selectEvidence = (eventIds: number[], eventId: number | null = null) => {
    setSelectedEvidenceIds(eventIds);
    setSelectedEventId(eventId ?? eventIds[0] ?? null);
  };

  const openRun = (runId: string) => {
    setWorkspaceMode("run");
    setSelectedRunId(runId);
    setComparedRunId(null);
    resetCompareSelection();
    resetEvidenceSelection();
  };

  const openCompare = (runId: string) => {
    const normalizedComparedRunId =
      runId === selectedRunId ? runs.find((run) => run.id !== selectedRunId)?.id ?? null : runId;

    if (!normalizedComparedRunId) {
      setError("Necesitas al menos dos runs para abrir el modo de comparacion.");
      return;
    }

    setWorkspaceMode("compare");
    setComparedRunId(normalizedComparedRunId);
    resetCompareSelection();
  };

  const isWorkspaceLoading = isRunDataLoading || (workspaceMode === "compare" && isCompareLoading);

  // ── Feature 5: Keyboard shortcuts ─────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      // Don't fire when typing in input/textarea
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if (e.key === "j" || e.key === "ArrowDown") {
        const idx = filteredRuns.findIndex((r) => r.id === selectedRunId);
        const next = filteredRuns[idx + 1];
        if (next) openRun(next.id);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        const idx = filteredRuns.findIndex((r) => r.id === selectedRunId);
        const prev = filteredRuns[idx - 1];
        if (prev) openRun(prev.id);
      } else if (e.key === "r" && !e.ctrlKey && !e.metaKey) {
        refreshRuns().catch(() => undefined);
      } else if (e.key === "1") {
        setActiveTerminalTab("console");
      } else if (e.key === "2") {
        setActiveTerminalTab("auditing");
      } else if (e.key === "3") {
        setActiveTerminalTab("output");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [filteredRuns, selectedRunId, openRun, refreshRuns]);

  return (
    <div className="layout-root" style={{ display: "flex", flexDirection: "column", height: "100vh", width: "100vw", overflow: "hidden", background: "var(--bg)" }}>
      <a className="skip-link" href="#workspace-main">
        Saltar al contenido principal
      </a>

      <header className="studio-topbar" aria-label="Workspace status and mode controls" style={{ padding: "0 16px", height: "40px", borderBottom: "1px solid var(--line)", display: "flex", flexDirection: "row", flexWrap: "nowrap", justifyContent: "space-between", alignItems: "center", background: "var(--surface)", flexShrink: 0, minWidth: 0, overflow: "hidden" }}>
        <div className="studio-title-block" style={{ display: "flex", alignItems: "baseline", gap: "12px", minWidth: 0, flex: "1 1 auto", overflow: "hidden" }}>
          <h1 style={{ margin: 0, fontSize: "0.95rem", letterSpacing: "0", fontWeight: 600 }}>Visor Agentico</h1>
          <p className="workflow-hint" style={{ margin: 0, opacity: 0.6, fontSize: "0.75rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            [Interactive Trace Pipeline]
          </p>
        </div>

        <div className="studio-command-center" style={{ display: "flex", flexDirection: "row", gap: "16px", alignItems: "center", width: "auto", flexShrink: 0 }}>
          <div className="status-chip-row" role="status" aria-live="polite" style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "nowrap" }}>
            <span className={`status-chip ${isAnyBusy ? "is-loading" : "is-ready"}`} style={{ fontSize: "0.7rem", padding: "2px 6px", borderRadius: "2px", background: isAnyBusy ? "rgba(226, 172, 59, 0.2)" : "transparent", border: isAnyBusy ? "1px solid transparent" : "1px solid var(--line)", color: isAnyBusy ? "#c28f27" : "var(--muted)", textTransform: "uppercase" }}>
              {isAnyBusy ? "Busy" : "Ready"}
            </span>
            <span className="status-chip is-muted" style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
              {selectedRun ? `Run ${selectedRun.id.substring(0,8)}` : "No run selected"}
            </span>
          </div>

          <div className="workspace-switch" role="group" aria-label="Workspace mode" style={{ display: "flex", gap: "2px", background: "rgba(0,0,0,0.05)", borderRadius: "2px", padding: "2px", width: "auto", flexShrink: 0 }}>
            <button
              type="button"
              className={`secondary-action mode-action ${workspaceMode === "dashboard" ? "active" : ""}`}
              aria-pressed={workspaceMode === "dashboard"}
              style={{ padding: "4px 12px", borderRadius: "2px", border: "none", fontSize: "0.75rem", background: workspaceMode === "dashboard" ? "var(--accent)" : "transparent", color: workspaceMode === "dashboard" ? "#fff" : "var(--text)", cursor: "pointer", fontWeight: workspaceMode === "dashboard" ? 500 : 400 }}
              onClick={() => {
                setWorkspaceMode("dashboard");
                resetCompareSelection();
              }}
            >
              Dashboard
            </button>
            <button
              type="button"
              className={`secondary-action mode-action ${workspaceMode === "run" ? "active" : ""}`}
              aria-pressed={workspaceMode === "run"}
              style={{ padding: "4px 12px", borderRadius: "2px", border: "none", fontSize: "0.75rem", background: workspaceMode === "run" ? "var(--accent)" : "transparent", color: workspaceMode === "run" ? "#fff" : "var(--text)", cursor: "pointer", fontWeight: workspaceMode === "run" ? 500 : 400 }}
              onClick={() => {
                setWorkspaceMode("run");
                resetCompareSelection();
              }}
            >
              Run View
            </button>
            <button
              type="button"
              className={`secondary-action mode-action ${workspaceMode === "compare" ? "active" : ""}`}
              aria-pressed={workspaceMode === "compare"}
              disabled={!selectedRunId || !hasComparableRuns || isAnyBusy}
              style={{ padding: "4px 12px", borderRadius: "2px", border: "none", fontSize: "0.75rem", background: workspaceMode === "compare" ? "var(--accent)" : "transparent", color: workspaceMode === "compare" ? "#fff" : "var(--text)", cursor: "pointer", fontWeight: workspaceMode === "compare" ? 500 : 400, opacity: (!selectedRunId || !hasComparableRuns || isAnyBusy) ? 0.5 : 1 }}
              onClick={() => {
                if (selectedRunId) {
                  openCompare(selectedRunId);
                }
              }}
            >
              Compare
            </button>
          </div>
        </div>
      </header>

      <div className="app-shell" style={{ height: "calc(100vh - 40px)", padding: "0", gap: "0", display: "flex", background: "var(--bg)", minWidth: 0 }}>
        {/* Left Sidebar - Explorer */}
        <aside className="run-rail" aria-label="Run controls" style={{ width: "300px", minWidth: "300px", display: "flex", flexDirection: "column", border: "none", background: "var(--surface)", borderRadius: 0, borderRight: "1px solid var(--line)", padding: 0, flexShrink: 0 }}>
          <section className="rail-section" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", padding: "0" }}>
            <div className="section-head" style={{ padding: "8px 16px", margin: 0, background: "transparent", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "1px", color: "var(--muted)" }}>Explorer / Runs</span>
              {/* ── Feature 1: live refresh indicator ── */}
              {selectedRun?.status === "running" && (
                <span style={{ fontSize: "0.62rem", color: "#c28f27", letterSpacing: "0.5px", animation: "pulse 1.5s infinite" }}>● LIVE</span>
              )}
            </div>
            <div style={{ padding: "0 16px 8px", display: "flex", flexDirection: "column", gap: "6px" }}>
              <input
                aria-label="Buscar run"
                value={runFilters.search ?? ""}
                onChange={(e) => setRunFilters((f) => ({ ...f, search: e.target.value || undefined }))}
                placeholder="Search runs..."
                autoComplete="off"
                style={{ borderRadius: "2px", border: "1px solid var(--line)", background: "var(--bg)", padding: "4px 8px", fontSize: "0.75rem", width: "100%" }}
              />
              <div style={{ display: "flex", gap: "4px" }}>
                <select
                  value={runFilters.status ?? ""}
                  onChange={(e) => setRunFilters((f) => ({ ...f, status: e.target.value || undefined }))}
                  style={{ flex: 1, borderRadius: "2px", border: "1px solid var(--line)", background: "var(--bg)", padding: "4px", fontSize: "0.7rem" }}
                >
                  <option value="">All statuses</option>
                  <option value="running">Running</option>
                  <option value="completed">Completed</option>
                  <option value="failed">Failed</option>
                </select>
                <select
                  value={runFilters.provider ?? ""}
                  onChange={(e) => setRunFilters((f) => ({ ...f, provider: e.target.value || undefined }))}
                  style={{ flex: 1, borderRadius: "2px", border: "1px solid var(--line)", background: "var(--bg)", padding: "4px", fontSize: "0.7rem" }}
                >
                  <option value="">All providers</option>
                  {Array.from(new Set(runs.map((r) => r.provider).filter(Boolean))).map((p) => (
                    <option key={p} value={p!}>{p}</option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={() => { setRunFilters({}); setRunSearch(""); }}
                style={{ fontSize: "0.7rem", padding: "2px 8px", border: "1px solid var(--line)", borderRadius: "2px", background: "transparent", color: "var(--muted)", cursor: "pointer" }}
              >
                Clear filters
              </button>
            </div>
            <div className="run-list" role="list" aria-label="Runs list" style={{ gap: "0", flex: 1, overflowY: "auto", padding: 0 }}>
              {isRefreshingRuns && runs.length === 0 && <p className="empty-copy" style={{ padding: "16px", fontSize: "0.8rem" }}>Loading runs...</p>}
              {!isRefreshingRuns && runs.length === 0 && <p className="empty-copy" style={{ padding: "16px", fontSize: "0.8rem" }}>No runs captured yet.</p>}
              {!isRefreshingRuns && runs.length > 0 && filteredRuns.length === 0 && (
                <p className="empty-copy" style={{ padding: "16px", fontSize: "0.8rem" }}>No results for this filter.</p>
              )}
              {filteredRuns.map((run) => (
                <button
                  type="button"
                  key={run.id}
                  className={`run-item ${run.id === selectedRunId ? "selected" : ""}`}
                  aria-current={run.id === selectedRunId ? "true" : undefined}
                  aria-label={`${run.agent_name}. ${run.goal}. Estado ${run.status}.`}
                  role="listitem"
                  onClick={() => openRun(run.id)}
                  style={{ borderRadius: 0, border: "none", background: run.id === selectedRunId ? "rgba(53, 81, 69, 0.08)" : "transparent", padding: "4px 16px", cursor: "pointer", display: "flex", gap: "8px", alignItems: "center", width: "100%", textAlign: "left", borderLeft: run.id === selectedRunId ? "2px solid var(--accent)" : "2px solid transparent" }}
                >
                  <span className={`status-dot status-${run.status}`} style={{ margin: 0, flexShrink: 0, width: "6px", height: "6px" }} />
                  <div style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
                    <strong style={{ fontSize: "0.8rem", color: run.id === selectedRunId ? "var(--accent)" : "var(--text)", display: "block", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: run.id === selectedRunId ? 600 : 400 }}>{run.agent_name}</strong>
                    <p style={{ fontSize: "0.7rem", margin: "0", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", opacity: 0.7 }}>{run.goal || "No goal specified"}</p>
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* ── Feature 3: Aggregate Stats Panel ── */}
          {globalStats && (
            <div style={{ borderTop: "1px solid var(--line)", padding: "10px 16px", background: "var(--bg)", flexShrink: 0 }}>
              <p style={{ margin: "0 0 6px", fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--muted)" }}>Session Stats</p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>Total</span>
                  <strong style={{ fontSize: "0.72rem" }}>{globalStats.total}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>OK</span>
                  <strong style={{ fontSize: "0.72rem", color: "#2e7d5a" }}>{globalStats.pct}%</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>Failed</span>
                  <strong style={{ fontSize: "0.72rem", color: globalStats.failed > 0 ? "#c0392b" : "var(--text)" }}>{globalStats.failed}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>Errors</span>
                  <strong style={{ fontSize: "0.72rem", color: globalStats.totalErrors > 0 ? "#c28f27" : "var(--text)" }}>{globalStats.totalErrors}</strong>
                </div>
              </div>
              {/* mini progress bar */}
              <div style={{ marginTop: "8px", height: "3px", background: "var(--line)", borderRadius: "2px", overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${globalStats.pct}%`, background: "#2e7d5a", borderRadius: "2px", transition: "width 0.4s ease" }} />
              </div>
            </div>
          )}
        </aside>

        {/* Central Editor Area */}
        <main id="workspace-main" className="workspace" aria-busy={isWorkspaceLoading} style={{ flex: 1, border: "none", background: "transparent", borderRadius: 0, display: "flex", flexDirection: "column", height: "100%", padding: 0, minWidth: 0, overflow: "hidden" }}>
          {/* Editor Tabs Group */}
          <section className="workspace-status-strip" aria-label="Analysis workflow" style={{ padding: "0", borderRadius: 0, display: "flex", background: "var(--bg)", borderBottom: "1px solid var(--line)", overflowX: "auto", maxWidth: "100%", minWidth: 0, position: "relative", zIndex: 1 }}>
            <article className={`workflow-step ${selectedRun ? "is-active" : ""}`} style={{ padding: "8px 16px", borderRight: "1px solid var(--line)", borderTop: selectedRun ? "2px solid var(--accent)" : "2px solid transparent", background: selectedRun ? "var(--surface)" : "var(--bg)", display: "flex", alignItems: "center", gap: "8px", minWidth: "120px", cursor: "default" }}>
              <span className={`status-dot ${selectedRun ? "status-completed" : ""}`} style={{ margin: 0, width: "6px", height: "6px" }} />
              <span style={{ fontSize: "0.75rem", color: selectedRun ? "var(--text)" : "var(--muted)", fontWeight: selectedRun ? 500 : 400, whiteSpace: "nowrap" }}>run_summary.md</span>
            </article>
            <article className={`workflow-step ${overview ? "is-active" : ""}`} style={{ padding: "8px 16px", borderRight: "1px solid var(--line)", borderTop: overview ? "2px solid var(--accent)" : "2px solid transparent", background: overview ? "var(--surface)" : "var(--bg)", display: "flex", alignItems: "center", gap: "8px", minWidth: "120px", cursor: "default" }}>
              <span style={{ fontSize: "0.75rem", color: overview ? "var(--text)" : "var(--muted)", fontWeight: overview ? 500 : 400, whiteSpace: "nowrap" }}>execution_trace.ts</span>
            </article>
            <article className={`workflow-step ${selectedEvents.length > 0 ? "is-active" : ""}`} style={{ padding: "8px 16px", borderRight: "1px solid var(--line)", borderTop: selectedEvents.length > 0 ? "2px solid var(--accent)" : "2px solid transparent", background: selectedEvents.length > 0 ? "var(--surface)" : "var(--bg)", display: "flex", alignItems: "center", gap: "8px", minWidth: "120px", cursor: "default" }}>
              <span style={{ fontSize: "0.75rem", color: selectedEvents.length > 0 ? "var(--text)" : "var(--muted)", fontWeight: selectedEvents.length > 0 ? 500 : 400, whiteSpace: "nowrap" }}>evidence_{selectedEvents.length}.json</span>
            </article>
          </section>

        {error && (
          <p id="workspace-error-banner" className="status-banner status-banner-error" role="alert">
            {error}
          </p>
        )}
        {isWorkspaceLoading && overview && (
          <p className="status-banner status-banner-loading" role="status" aria-live="polite">
            Actualizando panel con los ultimos eventos...
          </p>
        )}
          <div style={{ flex: 1, minHeight: 0, overflow: "auto", position: "relative" }}>
            {workspaceMode === "dashboard" ? (
              <DashboardView data={dashboard} isLoading={isDashboardLoading} />
            ) : !overview ? (
              <div className="empty-stage" style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
                <h2>Ready to chat</h2>
                <p>Start a new agent execution below, or select an existing one.</p>
              </div>
            ) : workspaceMode === "compare" ? (
              <CompareWorkspace
                runs={runs}
                selectedRunId={selectedRunId}
                comparedRunId={comparedRunId}
                compareData={compareData}
                error={error}
                isLoading={isCompareLoading}
                hasComparableRuns={hasComparableRuns}
                onSelectLeftRun={(runId) => {
                  setSelectedRunId(runId);
                  resetCompareSelection();
                }}
                onSelectRightRun={(runId) => {
                  setComparedRunId(runId);
                  resetCompareSelection();
                }}
                onBackToRun={() => {
                  setWorkspaceMode("run");
                  resetCompareSelection();
                }}
                onSelectionChange={setCompareSelection}
              />
            ) : (
              <RunWorkspace
                overview={overview}
                timeline={timeline}
                analytics={analytics}
                view={view}
                onViewChange={setView}
                mainFlow={mainFlow}
                toolFlow={toolFlow}
                maxToolDuration={maxToolDuration}
                similarFilters={similarFilters}
                comparedRunId={comparedRunId}
                selectedEventId={selectedEventId}
                selectedEvidenceIds={selectedEvidenceIds}
                isTimelineLoading={isRunDataLoading}
                isAnalyticsLoading={isAnalyticsLoading}
                onSimilarFiltersChange={setSimilarFilters}
                onSelectEvidence={selectEvidence}
                onCompareRun={openCompare}
                onOpenRun={openRun}
              />
            )}
          </div>

          {/* Terminal / Launch Console */}
          <div
            className="terminal-panel"
            style={{
              background: "var(--surface)",
              borderTop: "1px solid var(--line)",
              display: "flex",
              flexDirection: "column",
              flexShrink: 0,
              height: activeTerminalTab === "auditing" ? "340px" : undefined,
            }}
          >
            <div className="terminal-tabs" style={{ display: "flex", borderBottom: "1px solid var(--line)", background: "var(--bg)", flexShrink: 0 }}>
              <button
                onClick={() => setActiveTerminalTab("console")}
                style={{ padding: "6px 16px", border: "none", borderRight: "1px solid var(--line)", borderTop: activeTerminalTab === "console" ? "2px solid var(--accent)" : "2px solid transparent", background: activeTerminalTab === "console" ? "var(--surface)" : "transparent", fontSize: "0.7rem", textTransform: "uppercase", fontWeight: activeTerminalTab === "console" ? 600 : 400, color: activeTerminalTab === "console" ? "var(--text)" : "var(--muted)", letterSpacing: "1px", cursor: "pointer" }}
              >
                Agent Console
              </button>
              <button
                onClick={() => setActiveTerminalTab("auditing")}
                style={{ padding: "6px 16px", border: "none", borderRight: "1px solid var(--line)", borderTop: activeTerminalTab === "auditing" ? "2px solid var(--accent)" : "2px solid transparent", background: activeTerminalTab === "auditing" ? "var(--surface)" : "transparent", fontSize: "0.7rem", textTransform: "uppercase", fontWeight: activeTerminalTab === "auditing" ? 600 : 400, color: activeTerminalTab === "auditing" ? "var(--text)" : "var(--muted)", letterSpacing: "1px", cursor: "pointer" }}
              >
                Auditing Maps
              </button>
              <button
                onClick={() => setActiveTerminalTab("output")}
                style={{ padding: "6px 16px", border: "none", borderRight: "1px solid var(--line)", borderTop: activeTerminalTab === "output" ? "2px solid var(--accent)" : "2px solid transparent", background: activeTerminalTab === "output" ? "var(--surface)" : "transparent", fontSize: "0.7rem", textTransform: "uppercase", fontWeight: activeTerminalTab === "output" ? 600 : 400, color: activeTerminalTab === "output" ? "var(--text)" : "var(--muted)", letterSpacing: "1px", cursor: "not-allowed", opacity: 0.8 }}
              >
                Output
              </button>
              <button
                style={{ padding: "6px 16px", border: "none", borderRight: "1px solid var(--line)", borderTop: "2px solid transparent", background: "transparent", fontSize: "0.7rem", textTransform: "uppercase", fontWeight: 400, color: "var(--muted)", letterSpacing: "1px", cursor: "not-allowed", opacity: 0.8 }}
              >
                Terminal
              </button>
            </div>

            {/* Audit tab: full-height panel — rendered outside the compact dock */}
            {activeTerminalTab === "auditing" && (
              <div style={{ flex: 1, overflow: "hidden", minHeight: 0 }}>
                <AuditDashboard
                  audit={audit}
                  isLoading={isAuditLoading}
                  onSelectEvidence={selectEvidence}
                />
              </div>
            )}

            {/* Compact dock for console + output tabs */}
            {activeTerminalTab !== "auditing" && (
              <div className="chat-input-dock" style={{ zIndex: 10, padding: "12px 16px", margin: 0 }}>
                {activeTerminalTab === "console" && (
                  <>
                    <form className="launcher-form" data-testid="launcher-form" onSubmit={handleLaunchRun} style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <input
                          aria-label="Agent name"
                          value={launchForm.agentName}
                          onChange={(event) => updateLaunchField("agentName", event.target.value)}
                          placeholder="Agent (lmstudio-local-agent)"
                          autoComplete="off"
                          required
                          style={{ flex: 1, padding: "4px 8px", borderRadius: "2px", border: "1px solid var(--line)", fontSize: "0.75rem", background: "var(--bg)", fontFamily: "monospace" }}
                        />
                        <input
                          aria-label="Model"
                          value={launchForm.model}
                          onChange={(event) => updateLaunchField("model", event.target.value)}
                          placeholder="Model (google/gemma-4-e4b)"
                          autoComplete="off"
                          required
                          style={{ flex: 1, padding: "4px 8px", borderRadius: "2px", border: "1px solid var(--line)", fontSize: "0.75rem", background: "var(--bg)", fontFamily: "monospace" }}
                        />
                      </div>
                      <div style={{ display: "flex", gap: "8px", alignItems: "flex-end" }}>
                        <textarea
                          aria-label="User prompt"
                          value={launchForm.userPrompt}
                          onChange={(event) => updateLaunchField("userPrompt", event.target.value)}
                          placeholder=">_"
                          required
                          autoComplete="off"
                          style={{ flex: 1, minHeight: "24px", height: "40px", padding: "8px", borderRadius: "2px", border: "1px solid var(--line)", resize: "vertical", fontSize: "0.85rem", background: "var(--bg)", fontFamily: "monospace", color: "var(--text)" }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) {
                              e.preventDefault();
                              (e.target as HTMLTextAreaElement).form?.requestSubmit();
                            }
                          }}
                        />
                        <button type="submit" className="primary-action" disabled={isLaunchingRun} style={{ padding: "0 24px", height: "40px", borderRadius: "2px", background: "var(--accent)", color: "#fff", fontWeight: 600, border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.8rem", letterSpacing: "1px" }}>
                          {isLaunchingRun ? "..." : "EXEC"}
                        </button>
                      </div>
                    </form>
                    {launchNotice && <p className="launcher-notice" style={{ marginTop: "6px", fontSize: "0.7rem", color: "var(--accent)" }}>{launchNotice}</p>}
                  </>
                )}

                {activeTerminalTab === "output" && (
                  <div style={{ height: "200px", padding: "16px", fontFamily: "monospace", fontSize: "0.8rem", color: "var(--muted)", overflow: "auto" }}>
                    No output available.
                  </div>
                )}
              </div>
            )}
          </div>

        </main>

      {/* Right Sidebar - Inspector */}
      <aside
        className={`inspector ${isWorkspaceLoading ? "is-busy" : ""}`}
        aria-label="Inspector panel"
        aria-busy={isWorkspaceLoading}
        style={{ width: "340px", minWidth: "340px", borderLeft: "1px solid var(--line)", background: "var(--surface-strong)", borderTop: "none", borderRadius: 0, padding: 0, display: "flex", flexDirection: "column", flexShrink: 0, position: "relative", zIndex: 2, overflow: "hidden" }}
      >
        <div className="inspector-head" style={{ padding: "8px 16px", borderBottom: "1px solid var(--line)", background: "var(--surface-strong)", margin: 0, display: "flex", justifyContent: "space-between", alignItems: "center", position: "relative", zIndex: 1 }}>
          <span style={{ fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "1px", color: "var(--muted)" }}>Inspector</span>
        </div>
        <div style={{ flex: 1, padding: "16px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "16px" }}>
          <InspectorPanel
            workspaceMode={workspaceMode}
            overview={overview}
            explanation={explanation}
            artifacts={artifacts}
            selectedEvents={selectedEvents}
            selectedPrimaryEvent={selectedPrimaryEvent}
            compareLeftEvents={compareLeftEvents}
            compareRightEvents={compareRightEvents}
            comparePrimaryLeftEvent={comparePrimaryLeftEvent}
            comparePrimaryRightEvent={comparePrimaryRightEvent}
            onSelectEvidence={selectEvidence}
          />
        </div>
      </aside>
    </div>
    </div>
  );
}
