import { useState, useEffect, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  Position,
} from "@xyflow/react";
import type { GraphResponse, GraphNode, GraphEdge } from "../../types";
import { api } from "../../api";
import { decisionKindLabel, stepNodeLabel, truncate } from "../../lib/humanize";
import { formatDuration } from "../../lib/utils";
import { GitBranch, Map } from "lucide-react";

interface ExecutionGraphProps {
  runId: string | null;
  view?: "execution" | "decisions";
  /** Status of the open run: decisions only exist once it has ended. */
  runStatus?: string | null;
  onSelectNode?: (node: GraphNode | null) => void;
}

const NODE_STYLES: Record<string, { border: string; background: string }> = {
  event: { border: "#d4a76a", background: "#141414" },
  artifact: { border: "#3b82f6", background: "#141414" },
  decision: { border: "#f59e0b", background: "#141414" },
  default: { border: "#737373", background: "#141414" },
};

/** An execution node is a whole step: its name and how long it took. Other nodes keep their own label. */
function stepLabel(node: GraphNode): string {
  if (node.type !== "event") return node.label
  const duration = typeof node.data?.durationMs === "number" ? node.data.durationMs : null
  const title = stepNodeLabel(node.label, node.data)
  return duration === null ? title : `${title} · ${formatDuration(duration)}`
}

function buildFlowNodes(nodes: GraphNode[]): Node[] {
  return nodes.map((node) => {
    const isFailed =
      node.type === "event" &&
      (node.data?.status === "failed" || node.data?.status === "error");
    const style = isFailed
      ? { border: "#ef4444", background: "#141414" }
      : (NODE_STYLES[node.type] ?? NODE_STYLES.default);
    return {
      id: node.id,
      type: "default",
      position: node.position,
      // A long label (a whole script, for example) would make a huge node: the full text is in the inspector.
      data: { ...node.data, label: truncate(stepLabel(node), 60) },
      draggable: false,
      selectable: true,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      style: {
        borderRadius: 6,
        border: `1px solid ${style.border}`,
        padding: "8px 12px",
        width: 190,
        background: style.background,
        color: "#e5e5e5",
        fontSize: 12,
        fontFamily: "monospace",
        boxShadow: `0 0 0 1px ${style.border}20`,
      },
    };
  });
}

function buildFlowEdges(edges: GraphEdge[]): Edge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label ? decisionKindLabel(edge.label) : undefined,
    animated: edge.animated,
    style: { stroke: "#525252", strokeWidth: 1.5 },
    labelStyle: { fill: "#a3a3a3", fontSize: 9 },
    type: "default",
  }));
}

export function ExecutionGraph({ runId, view = "execution", runStatus, onSelectNode }: ExecutionGraphProps) {
  const [loaded, setLoaded] = useState<{ key: string; data: GraphResponse | null } | null>(null);
  const [showMinimap, setShowMinimap] = useState(false);
  // Loading and the graph itself are derived from which run/view the data was loaded for,
  // instead of toggling state from inside the effect.
  const key = runId ? `${runId}|${view}` : null;
  const graph = loaded?.key === key ? loaded.data : null;
  const loading = key !== null && loaded?.key !== key;

  useEffect(() => {
    if (!key || !runId) return;
    let isCurrent = true;
    api.getGraph(runId, view)
      .then((data) => { if (isCurrent) setLoaded({ key, data }); })
      .catch(() => { if (isCurrent) setLoaded({ key, data: null }); });
    return () => { isCurrent = false; };
  }, [key, runId, view]);

  const nodes = useMemo(() => (graph ? buildFlowNodes(graph.nodes) : []), [graph]);
  const edges = useMemo(() => (graph ? buildFlowEdges(graph.edges) : []), [graph]);

  const handleNodeClick = (_: React.MouseEvent, node: Node) => {
    const original = graph?.nodes.find((n) => n.id === node.id) ?? null;
    onSelectNode?.(original);
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted text-sm">
        Loading graph...
      </div>
    );
  }

  if (!graph || graph.nodes.length === 0) {
    const waiting = view === "decisions" && runStatus === "running";
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-1 text-muted text-sm text-center px-6">
        <p>{waiting ? "Decisions appear when the run finishes." : "No graph data available."}</p>
        {waiting && <p className="text-xs">This run is still running. Its steps are already in the Timeline.</p>}
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center justify-between px-4 py-2 border-b border-line bg-bg">
        <div className="flex items-center gap-2">
          <GitBranch className="w-3.5 h-3.5 text-accent" />
          <span className="text-xs font-medium">{view === "decisions" ? "Decision Graph" : "Execution Graph"}</span>
          <span className="text-[10px] text-muted bg-surface-strong px-1.5 py-0.5 rounded">
            {graph.nodes.length} nodes · {graph.edges.length} edges
          </span>
          {view === "decisions" && (
            <span className="text-[10px] text-muted">
              The key choices of the run: which tool was picked, retries and recoveries. Select one for its detail.
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-[10px] text-muted">
            <LegendItem color="#d4a76a" label="Event" />
            <LegendItem color="#ef4444" label="Failed" />
            <LegendItem color="#3b82f6" label="Artifact" />
            <LegendItem color="#f59e0b" label="Decision" />
          </div>
          <button
            onClick={() => setShowMinimap((s) => !s)}
            title="Toggle minimap"
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] border transition-colors ${
              showMinimap
                ? "bg-accent/10 border-accent/30 text-accent"
                : "bg-transparent border-line text-muted hover:text-text"
            }`}
          >
            <Map className="w-3 h-3" />
            Map
          </button>
        </div>
      </div>

      <div className="flex-1 relative">
        <ReactFlow
          key={`${runId}-${view}`}
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          onNodeClick={handleNodeClick}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={true}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} color="#262626" size={1} />
          <Controls showInteractive={false} />
          {showMinimap && (
            <MiniMap
              nodeStrokeWidth={2}
              nodeStrokeColor="#d4a76a"
              maskColor="rgba(0,0,0,0.7)"
              className="!bg-bg !border !border-line"
              pannable
              zoomable
            />
          )}
        </ReactFlow>
      </div>
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1">
      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      <span>{label}</span>
    </div>
  );
}
