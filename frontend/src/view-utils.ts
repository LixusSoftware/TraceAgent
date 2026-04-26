import { Position, type Edge, type Node } from "@xyflow/react";
import type { GraphResponse, RunOverview, SimilarRunFilters } from "./types";

export const defaultSimilarRunFilters: SimilarRunFilters = {
  sameAgentOnly: false,
  status: "all",
  sharedToolsOnly: false,
  minScore: 0.15,
  limit: 5
};

export function formatDuration(startedAt: string, endedAt: string | null): string {
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  const totalSeconds = Math.max(1, Math.round((end - start) / 1000));
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
}

export function formatWhen(timestamp: string | null): string {
  if (!timestamp) {
    return "-";
  }
  return new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "2-digit",
    month: "short"
  }).format(new Date(timestamp));
}

export function formatMs(value: number | null): string {
  if (value === null) {
    return "-";
  }
  if (value < 1000) {
    return `${value} ms`;
  }
  const seconds = value / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)} s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

export function prettifyState(value: string | null): string {
  if (!value) {
    return "unknown";
  }
  return value.split("_").join(" ");
}

export function formatMetadataValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatMetadataValue(item)).join(", ");
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function collectToolNames(overview: RunOverview | null): string[] {
  if (!overview) {
    return [];
  }
  return Array.from(new Set(overview.tool_chain.map((item) => item.tool_name))).sort();
}

export function formatDelta(base: number, other: number, unit = ""): string {
  const diff = other - base;
  if (diff === 0) {
    return `same${unit ? ` ${unit}` : ""}`;
  }
  const prefix = diff > 0 ? "+" : "";
  return `${prefix}${diff}${unit ? ` ${unit}` : ""}`;
}

export function buildFlow(graph: GraphResponse | null, palette: "main" | "tool" = "main"): { nodes: Node[]; edges: Edge[] } {
  if (!graph) {
    return { nodes: [], edges: [] };
  }

  const nodes: Node[] = graph.nodes.map((node) => ({
    id: node.id,
    type: "default",
    position: node.position,
    data: { ...node.data, label: node.label },
    draggable: false,
    selectable: true,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: {
      borderRadius: 20,
      border: "1px solid rgba(53, 81, 69, 0.18)",
      padding: 12,
      width: palette === "tool" ? 180 : 210,
      background:
        node.type === "decision"
          ? "#eff5ea"
          : node.type === "artifact"
            ? "#ebe4d6"
            : palette === "tool"
              ? "#edf2e8"
              : "#f9f7f2",
      color: "#20322c",
      boxShadow: "0 10px 20px rgba(25, 31, 28, 0.08)"
    }
  }));

  const edges: Edge[] = graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label ?? undefined,
    animated: edge.animated,
    style: { stroke: palette === "tool" ? "#708276" : "#50665d", strokeOpacity: 0.6 }
  }));
  return { nodes, edges };
}
