import { Calendar, Clock, Hash, Zap, Box, GitBranch } from "lucide-react"
import type { RunOverview, EventItem, GraphNode } from "../../types"
import { formatDuration, formatWhen } from "../../lib/utils"
import { JsonViewer } from "../JsonViewer"

interface InspectorProps {
  overview: RunOverview | null
  selectedEvent: EventItem | null
  selectedGraphNode?: GraphNode | null
}

export function Inspector({ overview, selectedEvent, selectedGraphNode }: InspectorProps) {
  return (
    <aside className="w-[340px] min-w-[340px] border-l border-line bg-surface-strong flex flex-col shrink-0 overflow-hidden">
      <div className="px-4 py-2 border-b border-line flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">Inspector</span>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {selectedGraphNode ? (
          <GraphNodeInspector node={selectedGraphNode} />
        ) : selectedEvent ? (
          <EventInspector event={selectedEvent} />
        ) : overview ? (
          <RunInspector overview={overview} />
        ) : (
          <p className="text-xs text-muted text-center py-8">Select a run, event, or graph node to inspect.</p>
        )}
      </div>
    </aside>
  )
}

function GraphNodeInspector({ node }: { node: GraphNode }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-warning/10 text-warning border border-warning/20">
            {node.type}
          </span>
        </div>
        <p className="text-sm font-medium">{node.label}</p>
      </div>

      <div className="space-y-1 text-xs">
        <Row label="ID" value={node.id} />
        <Row label="Type" value={node.type} />
        <Row label="X" value={Math.round(node.position.x)} />
        <Row label="Y" value={Math.round(node.position.y)} />
      </div>

      {node.data && Object.keys(node.data).length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Data</p>
          <JsonViewer value={node.data} maxHeight="240px" />
        </div>
      )}
    </div>
  )
}

function RunInspector({ overview }: { overview: RunOverview }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold mb-1">{overview.agent_name}</h3>
        <p className="text-xs text-muted">{overview.goal}</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat icon={Hash} label="Tools" value={overview.tool_count} />
        <Stat icon={Zap} label="Errors" value={overview.error_count} />
        <Stat icon={Clock} label="Duration" value={formatDuration(overview.execution.duration_ms)} />
        <Stat icon={Calendar} label="Started" value={formatWhen(overview.started_at)} />
      </div>

      <div className="space-y-1">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Execution</p>
        <div className="space-y-1 text-xs">
          <Row label="Status" value={overview.status} />
          <Row label="Provider" value={overview.provider ?? "—"} />
          <Row label="Model" value={overview.model ?? "—"} />
          <Row label="Turns" value={overview.execution.model_turn_count} />
          <Row label="Commands" value={overview.execution.command_count} />
        </div>
      </div>

      {overview.flags.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Flags</p>
          <div className="flex flex-wrap gap-1">
            {overview.flags.map((f, i) => (
              <span
                key={i}
                className={`text-[10px] px-1.5 py-0.5 rounded border ${
                  f.type === "error" ? "border-danger/30 text-danger bg-danger/10" :
                  f.type === "warning" ? "border-warning/30 text-warning bg-warning/10" :
                  "border-info/30 text-info bg-info/10"
                }`}
              >
                {f.label}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function EventInspector({ event }: { event: EventItem }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/20">
            {event.type}
          </span>
          <span className="text-[10px] text-muted">{event.actor}</span>
        </div>
        <p className="text-sm">{event.summary}</p>
      </div>

      <div className="space-y-1 text-xs">
        <Row label="Status" value={event.status ?? "—"} />
        <Row label="Duration" value={formatDuration(event.duration_ms)} />
        <Row label="Timestamp" value={formatWhen(event.timestamp)} />
        <Row label="Step ID" value={event.step_id ?? "—"} />
        <Row label="Parent" value={event.parent_step_id ?? "—"} />
        {event.provider && <Row label="Provider" value={event.provider} />}
        {event.model && <Row label="Model" value={event.model} />}
        {event.tool_name && <Row label="Tool" value={event.tool_name} />}
      </div>

      {event.metadata && Object.keys(event.metadata).length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Metadata</p>
          <JsonViewer value={event.metadata} maxHeight="160px" />
        </div>
      )}

      {event.payload_full && (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Payload</p>
          <JsonViewer value={event.payload_full} maxHeight="240px" />
        </div>
      )}
    </div>
  )
}

function Stat({ icon: Icon, label, value }: { icon: typeof Hash; label: string; value: React.ReactNode }) {
  return (
    <div className="bg-surface border border-line rounded-md p-2">
      <div className="flex items-center gap-1.5 text-muted mb-1">
        <Icon className="w-3 h-3" />
        <span className="text-[10px] uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-sm font-semibold">{value}</p>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between py-0.5 border-b border-line/50">
      <span className="text-muted">{label}</span>
      <span className="font-medium truncate max-w-[180px]">{value}</span>
    </div>
  )
}
