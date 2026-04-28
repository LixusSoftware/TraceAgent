import { useState, useEffect } from "react";
import { GitCompare, ArrowRight, AlertCircle, CheckCircle2, Minus, ChevronDown, ChevronRight, Circle } from "lucide-react";
import type { RunListItem, RunCompareResponse, DiffPair } from "../../types";
import { api } from "../../api";
import { formatDuration, formatWhen } from "../../lib/utils";
import { JsonViewer } from "../JsonViewer";

interface CompareViewProps {
  runs: RunListItem[];
}

export function CompareView({ runs }: CompareViewProps) {
  const [leftRunId, setLeftRunId] = useState<string>("");
  const [rightRunId, setRightRunId] = useState<string>("");
  const [result, setResult] = useState<RunCompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedDiffs, setExpandedDiffs] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (runs.length >= 2 && !leftRunId && !rightRunId) {
      setLeftRunId(runs[0].id);
      setRightRunId(runs[1].id);
    }
  }, [runs, leftRunId, rightRunId]);

  const handleCompare = async () => {
    if (!leftRunId || !rightRunId || leftRunId === rightRunId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.compareRuns(leftRunId, rightRunId);
      setResult(data);
    } catch (e) {
      setError("Failed to compare runs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (leftRunId && rightRunId && leftRunId !== rightRunId) {
      handleCompare();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leftRunId, rightRunId]);

  const toggleDiff = (key: string) => {
    setExpandedDiffs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="flex items-center gap-2 mb-6">
        <GitCompare className="w-4 h-4 text-accent" />
        <h2 className="text-lg font-semibold">Compare Runs</h2>
      </div>

      {/* Run Selectors */}
      <div className="flex items-center gap-3 mb-6">
        <RunSelect runs={runs} value={leftRunId} onChange={setLeftRunId} label="Left run" />
        <ArrowRight className="w-4 h-4 text-muted shrink-0" />
        <RunSelect runs={runs} value={rightRunId} onChange={setRightRunId} label="Right run" />
      </div>

      {loading && <p className="text-sm text-muted">Comparing...</p>}
      {error && <p className="text-sm text-danger">{error}</p>}

      {!loading && !error && result && (
        <div className="space-y-6">
          {/* Overview Cards */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <RunCard run={result.left_run} title="Left" />
            <RunCard run={result.right_run} title="Right" />
          </div>

          {/* Overview Diff */}
          <div className="bg-surface border border-line rounded-lg p-4">
            <h3 className="text-sm font-medium mb-3">Overview Diff</h3>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              <DiffStat label="Tools" delta={result.overview_diff.tool_count_delta} />
              <DiffStat label="Commands" delta={result.overview_diff.command_count_delta} />
              <DiffStat label="Errors" delta={result.overview_diff.error_count_delta} />
              <DiffStat label="Retries" delta={result.overview_diff.retry_count_delta} />
              <DiffStat label="Artifacts" delta={result.overview_diff.artifact_count_delta} />
              <DiffStat label="Tokens" delta={result.overview_diff.token_total_delta} />
              <DiffStat label="Duration (ms)" delta={result.overview_diff.duration_ms_delta} />
            </div>
          </div>

          {/* Divergence */}
          {result.divergence && (
            <div className="bg-surface border border-line rounded-lg p-4">
              <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
                <AlertCircle className="w-3.5 h-3.5 text-warning" />
                First Divergence
              </h3>
              <p className="text-xs text-muted mb-1">{result.divergence.summary}</p>
              <p className="text-[11px] text-muted">Kind: <span className="text-text">{result.divergence.first_mismatch_kind}</span></p>
            </div>
          )}

          {/* Root Cause */}
          {result.root_cause && (
            <div className="bg-surface border border-line rounded-lg p-4">
              <h3 className="text-sm font-medium mb-2">Root Cause Analysis</h3>
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${
                  result.root_cause.confidence === "high" ? "border-accent/30 text-accent bg-accent/10" :
                  result.root_cause.confidence === "medium" ? "border-warning/30 text-warning bg-warning/10" :
                  "border-info/30 text-info bg-info/10"
                }`}>
                  {result.root_cause.confidence} confidence
                </span>
              </div>
              <p className="text-xs font-medium mb-1">{result.root_cause.label}</p>
              <p className="text-xs text-muted mb-2">{result.root_cause.summary}</p>
              <p className="text-[11px] text-muted">Impact: {result.root_cause.impact_summary}</p>
            </div>
          )}

          {/* Timeline Diff */}
          <DiffSection
            title="Timeline Diff"
            items={result.aligned_timeline}
            expanded={expandedDiffs.has("timeline")}
            onToggle={() => toggleDiff("timeline")}
          />

          {/* Tool Diff */}
          <DiffSection
            title="Tool Diff"
            items={result.tool_diff}
            expanded={expandedDiffs.has("tools")}
            onToggle={() => toggleDiff("tools")}
          />

          {/* Command Diff */}
          <DiffSection
            title="Command Diff"
            items={result.command_diff}
            expanded={expandedDiffs.has("commands")}
            onToggle={() => toggleDiff("commands")}
          />

          {/* File Diff */}
          <DiffSection
            title="File Diff"
            items={result.file_diff}
            expanded={expandedDiffs.has("files")}
            onToggle={() => toggleDiff("files")}
          />
        </div>
      )}

      {!loading && !error && !result && (
        <p className="text-sm text-muted">Select two different runs to compare.</p>
      )}
    </div>
  );
}

function RunSelect({
  runs,
  value,
  onChange,
  label,
}: {
  runs: RunListItem[];
  value: string;
  onChange: (id: string) => void;
  label: string;
}) {
  return (
    <div className="flex-1 min-w-0">
      <label className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-1 block">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full text-xs bg-bg border border-line rounded-md px-2 py-1.5 focus:outline-none focus:border-accent truncate"
      >
        <option value="">Select a run...</option>
        {runs.map((run) => (
          <option key={run.id} value={run.id}>
            {run.agent_name} · {run.id.slice(0, 8)} · {run.status}
          </option>
        ))}
      </select>
    </div>
  );
}

function RunCard({ run, title }: { run: { agent_name: string; goal: string; status: string; tool_count: number; error_count: number; started_at: string; execution: { duration_ms: number | null; model_turn_count: number; command_count: number } }; title: string }) {
  return (
    <div className="bg-surface border border-line rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">{title}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${
          run.status === "completed" ? "border-accent/30 text-accent bg-accent/10" :
          run.status === "failed" ? "border-danger/30 text-danger bg-danger/10" :
          "border-warning/30 text-warning bg-warning/10"
        }`}>
          {run.status}
        </span>
      </div>
      <h4 className="text-sm font-medium mb-1">{run.agent_name}</h4>
      <p className="text-xs text-muted mb-3 truncate">{run.goal}</p>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between">
          <span className="text-muted">Tools</span>
          <span className="font-medium">{run.tool_count}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted">Errors</span>
          <span className="font-medium">{run.error_count}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted">Turns</span>
          <span className="font-medium">{run.execution.model_turn_count}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted">Commands</span>
          <span className="font-medium">{run.execution.command_count}</span>
        </div>
        <div className="flex justify-between col-span-2">
          <span className="text-muted">Duration</span>
          <span className="font-medium">{formatDuration(run.execution.duration_ms)}</span>
        </div>
      </div>
    </div>
  );
}

function DiffStat({ label, delta }: { label: string; delta: number | null }) {
  if (delta === null) {
    return (
      <div className="bg-bg border border-line rounded p-2">
        <p className="text-[10px] text-muted">{label}</p>
        <p className="text-sm font-medium text-muted">—</p>
      </div>
    );
  }
  const isPositive = delta > 0;
  const isNegative = delta < 0;
  return (
    <div className="bg-bg border border-line rounded p-2">
      <p className="text-[10px] text-muted">{label}</p>
      <div className="flex items-center gap-1">
        {isPositive && <ChevronRight className="w-3 h-3 text-accent rotate-[-90deg]" />}
        {isNegative && <ChevronRight className="w-3 h-3 text-danger rotate-90" />}
        {!isPositive && !isNegative && <Minus className="w-3 h-3 text-muted" />}
        <span className={`text-sm font-medium ${isPositive ? "text-accent" : isNegative ? "text-danger" : "text-muted"}`}>
          {delta > 0 ? `+${delta}` : delta}
        </span>
      </div>
    </div>
  );
}

function DiffSection({
  title,
  items,
  expanded,
  onToggle,
}: {
  title: string;
  items: DiffPair[];
  expanded: boolean;
  onToggle: () => void;
}) {
  if (items.length === 0) return null;

  return (
    <div className="bg-surface border border-line rounded-lg">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 w-full text-left px-4 py-3 hover:bg-surface-strong transition-colors"
      >
        {expanded ? <ChevronDown className="w-3.5 h-3.5 text-muted" /> : <ChevronRight className="w-3.5 h-3.5 text-muted" />}
        <span className="text-sm font-medium">{title}</span>
        <span className="text-[10px] text-muted ml-auto">{items.length} items</span>
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-2">
          {items.map((item, i) => (
            <DiffRow key={i} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function DiffRow({ item }: { item: DiffPair }) {
  const relationColors: Record<string, string> = {
    shared: "border-info/30 text-info bg-info/10",
    left_only: "border-accent/30 text-accent bg-accent/10",
    right_only: "border-warning/30 text-warning bg-warning/10",
    different: "border-danger/30 text-danger bg-danger/10",
  };

  return (
    <div className="bg-bg border border-line rounded p-2">
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${relationColors[item.relation] ?? relationColors.different}`}>
          {item.relation.replace("_", " ")}
        </span>
        <span className="text-[11px] font-medium">{item.kind}</span>
      </div>
      <p className="text-[11px] text-muted mb-1">{item.summary}</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        {item.left && (
          <div className="border border-line/50 rounded p-1.5">
            <div className="flex items-center gap-1 mb-1">
              <CheckCircle2 className="w-3 h-3 text-accent" />
              <span className="text-[10px] font-medium">Left</span>
            </div>
            <p className="text-[10px] text-muted">{item.left.summary ?? "—"}</p>
            {item.left.metadata && Object.keys(item.left.metadata).length > 0 && (
              <JsonViewer value={item.left.metadata} maxHeight="80px" />
            )}
          </div>
        )}
        {item.right && (
          <div className="border border-line/50 rounded p-1.5">
            <div className="flex items-center gap-1 mb-1">
              <Circle className="w-3 h-3 text-info" fill="currentColor" />
              <span className="text-[10px] font-medium">Right</span>
            </div>
            <p className="text-[10px] text-muted">{item.right.summary ?? "—"}</p>
            {item.right.metadata && Object.keys(item.right.metadata).length > 0 && (
              <JsonViewer value={item.right.metadata} maxHeight="80px" />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
