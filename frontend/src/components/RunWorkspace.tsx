import { motion } from "framer-motion";
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";
import { SimilarRunsPanel } from "./SimilarRunsPanel";
import type {
  EventItem,
  RunAnalytics,
  RunOverview,
  SimilarRunFilters,
  TimelineResponse,
  ToolMetric
} from "../types";

import { formatDuration, formatMs, formatWhen, prettifyState } from "../view-utils";

type RunWorkspaceProps = {
  overview: RunOverview;
  timeline: TimelineResponse | null;
  analytics: RunAnalytics | null;
  view: "execution" | "decisions";
  isTimelineLoading: boolean;
  isAnalyticsLoading: boolean;
  onViewChange: (view: "execution" | "decisions") => void;
  mainFlow: { nodes: Node[]; edges: Edge[] };
  toolFlow: { nodes: Node[]; edges: Edge[] };
  maxToolDuration: number;
  similarFilters: SimilarRunFilters;
  comparedRunId: string | null;
  selectedEventId: number | null;
  selectedEvidenceIds: number[];
  onSimilarFiltersChange: (filters: SimilarRunFilters) => void;
  onSelectEvidence: (eventIds: number[], eventId?: number | null) => void;
  onCompareRun: (runId: string) => void;
  onOpenRun: (runId: string) => void;
};

export function RunWorkspace({
  overview,
  timeline,
  analytics,
  view,
  isTimelineLoading,
  isAnalyticsLoading,
  onViewChange,
  mainFlow,
  toolFlow,
  maxToolDuration,
  similarFilters,
  comparedRunId,
  selectedEventId,
  selectedEvidenceIds,
  onSimilarFiltersChange,
  onSelectEvidence,
  onCompareRun,
  onOpenRun
}: RunWorkspaceProps) {

  // ── Feature 4: Total cost from analytics tool_metrics ──────────────────────
  const totalCostUsd = analytics?.tool_metrics
    .reduce((sum, m) => sum + (m.estimated_cost_usd ?? 0), 0) ?? null;

  // ── Feature 2: Export run as Markdown ────────────────────────────────────
  const exportRunMarkdown = () => {
    const lines: string[] = [
      `# Run Report: ${overview.agent_name}`,
      ``,
      `**Goal:** ${overview.goal || "(no goal)"}`,
      `**Status:** ${overview.status}  |  **Run ID:** ${overview.id}`,
      `**Model:** ${overview.provider ?? "?"} / ${overview.model ?? "?"}`,
      `**Duration:** ${formatDuration(overview.started_at, overview.ended_at)}`,
      `**Started:** ${overview.started_at}`,
      ``,
      `## Metrics`,
      `| Metric | Value |`,
      `|--------|-------|`,
      `| Tools used | ${overview.tool_count} |`,
      `| Events | ${overview.execution.total_event_count} |`,
      `| Turns | ${overview.execution.model_turn_count} |`,
      `| Errors | ${overview.error_count} |`,
      `| Retries | ${overview.retry_count} |`,
      `| Total tokens | ${overview.execution.token_usage.total_tokens} |`,
    ];

    if (totalCostUsd !== null && totalCostUsd > 0) {
      lines.push(`| Est. cost | $${totalCostUsd.toFixed(4)} |`);
    }

    if (overview.tool_chain.length > 0) {
      lines.push(``, `## Tool Chain`);
      lines.push(...overview.tool_chain.map((t) => `- \`${t.tool_name}\` — ${t.status}`));
    }

    if (overview.flags && overview.flags.length > 0) {
      lines.push(``, `## Flags`);
      lines.push(...overview.flags.map((f) => `- **${f.type}**: ${f.label}`));
    }

    if (timeline?.groups && timeline.groups.length > 0) {
      const flatEvents = timeline.groups.flatMap((g) => g.events).slice(0, 20);
      if (flatEvents.length > 0) {
        lines.push(``, `## Timeline (first 20 events)`);
        lines.push(...flatEvents.map((e: EventItem) => `- \`${e.type}\` seq=${e.seq}${e.summary ? " — " + e.summary : ""}`));
      }
    }

    lines.push(``, `---`, `*Exported from Visor Agentico · ${new Date().toLocaleString()}*`);

    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `run_${overview.id.substring(0, 8)}_report.md`;
    a.click();
    URL.revokeObjectURL(url);
  };


  return (
    <>
      {/* ── Compact Audit Record Header ── */}
      <motion.header
        className="run-header"
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
      >
        {/* Top: identity bar */}
        <div className="run-header-identity">
          <div className="run-header-left">
            <span className="run-id-label">RUN</span>
            <span className="run-id-value" title={overview.id}>{overview.id.substring(0, 8)}</span>
            <span className="run-sep">/</span>
            <span className="run-agent-label">{overview.agent_name}</span>
            <span className={`state-pill state-${overview.status}`}>{prettifyState(overview.execution.current_state)}</span>
          </div>
          <div className="run-header-right">
            <span className="run-meta-chip">{overview.provider ?? "?"} / {overview.model ?? "?"}</span>
            <span className="run-meta-chip">{formatDuration(overview.started_at, overview.ended_at)}</span>
            {/* ── Feature 2: Export button ── */}
            <button
              type="button"
              title="Export run as Markdown report"
              onClick={exportRunMarkdown}
              className="run-export-btn"
            >
              ↓ MD
            </button>
          </div>
        </div>

        {/* Goal line */}
        <div className="run-goal-line">
          <span className="run-goal-eyebrow">OBJECTIVE</span>
          <span className="run-goal-text">{overview.goal || "(no goal specified)"}</span>
        </div>

        {/* Bottom: metrics strip */}
        <div className="run-metrics-strip">
          <div className="run-metric"><span>TOOLS</span><strong>{overview.tool_count}</strong></div>
          <div className="run-metric"><span>EVENTS</span><strong>{overview.execution.total_event_count}</strong></div>
          <div className="run-metric"><span>TURNS</span><strong>{overview.execution.model_turn_count}</strong></div>
          <div className="run-metric run-metric--alert" data-alert={overview.error_count > 0}>
            <span>ERRORS</span>
            <strong style={{ color: overview.error_count > 0 ? "#c0392b" : undefined }}>{overview.error_count}</strong>
          </div>
          <div className="run-metric"><span>RETRIES</span><strong>{overview.retry_count}</strong></div>
          <div className="run-metric"><span>TOKENS</span><strong>{overview.execution.token_usage.total_tokens.toLocaleString()}</strong></div>
          {totalCostUsd !== null && totalCostUsd > 0 && (
            <div className="run-metric">
              <span>COST</span>
              <strong style={{ color: "#c28f27" }}>${totalCostUsd.toFixed(4)}</strong>
            </div>
          )}
        </div>
      </motion.header>

      {/* ── Execution Log ── */}
      <section className="workspace-section" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div className="audit-log-header">
          <div className="audit-log-header-left">
            <span className="audit-log-label">EXECUTION TRACE</span>
            <span className="audit-log-sublabel">sequential event log</span>
          </div>
          {timeline && (
            <span className="audit-log-count">{timeline.groups.reduce((n, g) => n + g.events.length, 0)} events</span>
          )}
        </div>

        <div className="timeline-chat-view" style={{ flex: 1, display: "flex", flexDirection: "column", overflowY: "auto", background: "var(--bg)" }}>
          <section className="timeline-stage" aria-busy={isTimelineLoading} style={{ flex: 1, border: "none", background: "transparent", padding: 0 }}>
            <div aria-live="polite" style={{ display: "flex", flexDirection: "column" }}>
              {isTimelineLoading && (
                <p className="empty-copy" role="status" style={{ padding: "12px 16px", fontFamily: "monospace", fontSize: "0.75rem" }}>
                  &gt; Fetching trace...
                </p>
              )}
              {!isTimelineLoading && !timeline?.groups.length && (
                <p className="empty-copy" style={{ padding: "12px 16px", fontFamily: "monospace", fontSize: "0.75rem" }}>&gt; No trace events captured.</p>
              )}
              {!isTimelineLoading &&
                timeline?.groups.map((group) => (
                  <div key={group.step_id} className="audit-group">
                    <div className="audit-group-head">
                      <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                        <span className="audit-group-label">{group.label}</span>
                        <span className="audit-group-status">{group.status}</span>
                      </div>
                      <span className="audit-group-meta">{group.event_count} evt · {formatMs(group.duration_ms)}</span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column" }}>
                    {group.events.map((event) => {
                      const isUser = event.type.toLowerCase().includes("user") || event.type.toLowerCase().includes("prompt");
                      const isTool = event.type.toLowerCase().includes("tool") || event.type.toLowerCase().includes("call");
                      const isSelected = selectedEventId === event.id || selectedEvidenceIds.includes(event.id);
                      return (
                      <button
                        type="button"
                        key={event.id}
                        className={`audit-event-row${isSelected ? " audit-event-row--active" : ""}`}
                        onClick={() => onSelectEvidence([event.id], event.id)}
                      >
                        <span className="audit-event-type" data-user={isUser} data-tool={isTool}
                          style={{ color: isUser ? "var(--text)" : (isTool ? "#c28f27" : "var(--accent)") }}
                        >{event.type}</span>
                        <div className="audit-event-body">
                          <p className="audit-event-summary">{event.summary}</p>
                        </div>
                        <div className="audit-event-meta">
                          <span className="audit-event-time">{formatWhen(event.timestamp)}</span>
                          {event.duration_ms && (
                            <span className="audit-event-dur">{event.duration_ms} ms</span>
                          )}
                        </div>
                      </button>
                    )})}
                    </div>
                  </div>
                ))}
            </div>
          </section>

        </div>
      </section>

      {/* ── Execution / Decision Flow Graph ── */}
      <section style={{ borderTop: "1px solid var(--line)", padding: "12px 16px", background: "var(--surface)", flexShrink: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
          <span style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--muted)" }}>
            Flow map
          </span>
          <div style={{ display: "flex", gap: "4px" }}>
            <button
              type="button"
              onClick={() => onViewChange("execution")}
              style={{ padding: "2px 10px", fontSize: "0.68rem", fontWeight: view === "execution" ? 700 : 400, border: "1px solid var(--line)", borderRadius: "2px", background: view === "execution" ? "var(--accent)" : "transparent", color: view === "execution" ? "#fff" : "var(--muted)", cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.5px" }}
            >
              Execution
            </button>
            <button
              type="button"
              onClick={() => onViewChange("decisions")}
              style={{ padding: "2px 10px", fontSize: "0.68rem", fontWeight: view === "decisions" ? 700 : 400, border: "1px solid var(--line)", borderRadius: "2px", background: view === "decisions" ? "var(--accent)" : "transparent", color: view === "decisions" ? "#fff" : "var(--muted)", cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.5px" }}
            >
              Decisions
            </button>
          </div>
        </div>
        <div style={{ height: "260px", borderRadius: "4px", border: "1px solid var(--line)", overflow: "hidden" }}>
          <ReactFlow
            nodes={mainFlow.nodes}
            edges={mainFlow.edges}
            fitView
            onNodeClick={(_, node) => {
              const ids = (node.data.evidenceIds as number[] | undefined) ?? [];
              onSelectEvidence(ids, ids[0] ?? null);
            }}
          >
            <MiniMap pannable zoomable />
            <Controls showInteractive={false} />
            <Background gap={24} color="rgba(42, 67, 58, 0.08)" />
          </ReactFlow>
        </div>
        {mainFlow.nodes.length === 0 && (
          <p style={{ margin: "6px 0 0", fontSize: "0.75rem", color: "var(--muted)", fontFamily: "monospace" }}>
            &gt; No hay nodos para este modo de vista.
          </p>
        )}
      </section>

      <details className="workspace-section" style={{ background: "rgba(240, 240, 240, 0.5)", borderRadius: "12px", padding: "16px", margin: "16px 0", border: "1px solid rgba(47, 64, 57, 0.1)" }}>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          Expand Analytics & Tools Comparison
        </summary>
        <div style={{ marginTop: "16px" }}>
          <div className="workspace-section-head">
            <div>
              <p className="eyebrow">Analytics</p>
              <h3>Compare opportunities</h3>
            </div>
            <p className="section-note">Primero identifica runs vecinos, luego valida coste/latencia y finalmente dependencias de tool.</p>
          </div>

          <div className="analytics-grid">
            <SimilarRunsPanel
              analytics={analytics}
              comparedRunId={comparedRunId}
              filters={similarFilters}
              isLoading={isAnalyticsLoading}
              onFiltersChange={onSimilarFiltersChange}
              onCompare={onCompareRun}
              onOpen={onOpenRun}
            />

            <section className="panel-surface" aria-busy={isAnalyticsLoading}>
              <div className="section-head">
                <span>Cost / Latency</span>
                <small>{analytics?.tool_metrics.length ?? 0} tools</small>
              </div>
              <div className="metric-bars" aria-live="polite">
                {isAnalyticsLoading && (
                  <p className="empty-copy" role="status">
                    Actualizando metricas...
                  </p>
                )}
                {analytics?.tool_metrics.map((metric: ToolMetric) => (
                  <div key={metric.tool_name} className="tool-metric-row">
                    <div className="tool-metric-head">
                      <strong>{metric.tool_name}</strong>
                      <small>{metric.call_count} calls</small>
                    </div>
                    <div className="latency-bar">
                      <span
                        className="latency-bar-fill"
                        style={{ width: `${Math.max(10, (metric.total_duration_ms / maxToolDuration) * 100)}%` }}
                      />
                    </div>
                    <div className="tool-metric-values">
                      <span>{formatMs(metric.avg_duration_ms)} avg</span>
                      <span>{metric.attributed_total_tokens} tok</span>
                      <span>{metric.estimated_cost_usd !== null ? `$${metric.estimated_cost_usd.toFixed(4)}` : "cost n/a"}</span>
                    </div>
                  </div>
                ))}
                {!isAnalyticsLoading && !analytics?.tool_metrics.length && <p className="empty-copy">No hay metricas de tools para este run.</p>}
              </div>
            </section>

            <section className="panel-surface" aria-busy={isAnalyticsLoading}>
              <div className="section-head">
                <span>Tool graph</span>
                <small>{analytics?.tool_graph.nodes.length ?? 0} nodes</small>
              </div>
              <div className="compact-graph-frame" role="region" aria-label="Tool dependency map">
                <ReactFlow
                  nodes={toolFlow.nodes}
                  edges={toolFlow.edges}
                  fitView
                  onNodeClick={(_, node) => {
                    const ids = (node.data.evidenceIds as number[] | undefined) ?? [];
                    onSelectEvidence(ids, ids[0] ?? null);
                  }}
                >
                  <MiniMap pannable zoomable />
                  <Controls showInteractive={false} />
                  <Background gap={20} color="rgba(42, 67, 58, 0.06)" />
                </ReactFlow>
              </div>
              {analytics && analytics.tool_graph.nodes.length === 0 && (
                <p className="empty-copy graph-empty">No hay dependencias de tool para este run.</p>
              )}
            </section>
          </div>
        </div>
      </details>
    </>
  );
}
