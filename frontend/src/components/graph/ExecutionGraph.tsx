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
import { GitBranch, Map } from "lucide-react";

interface ExecutionGraphProps {
  runId: string | null;
  view?: "execution" | "decisions";
  onSelectNode?: (node: GraphNode | null) => void;
}

const NODE_STYLES: Record<string, { border: string; background: string }> = {
  event: { border: "#d4a76a", background: "#141414" },
  artifact: { border: "#3b82f6", background: "#141414" },
  decision: { border: "#f59e0b", background: "#141414" },
  default: { border: "#737373", background: "#141414" },
};

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
      data: { label: node.label, ...node.data },
      draggable: false,
      selectable: true,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      style: {
        borderRadius: 6,
        border: `1px solid ${style.border}`,
        padding: "8px 12px",
        width: 160,
        background: style.background,
        color: "#e5e5e5",
        fontSize: 10,
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
    label: edge.label ?? undefined,
    animated: edge.animated,
    style: { stroke: "#525252", strokeWidth: 1.5 },
    labelStyle: { fill: "#a3a3a3", fontSize: 9 },
    type: "default",
  }));
}

export function ExecutionGraph({ runId, view = "execution", onSelectNode }: ExecutionGraphProps) {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [showMinimap, setShowMinimap] = useState(false);

  useEffect(() => {
    if (!runId) {
      setGraph(null);
      return;
    }
    let isCurrent = true;
    setLoading(true);
    api.getGraph(runId, view)
      .then((data) => {
        if (isCurrent) setGraph(data);
      })
      .catch(() => { if (isCurrent) setGraph(null); })
      .finally(() => { if (isCurrent) setLoading(false); });
    return () => { isCurrent = false; };
  }, [runId, view]);

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
    return (
      <div className="flex-1 flex items-center justify-center text-muted text-sm">
        No graph data available.
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
