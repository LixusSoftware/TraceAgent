import { Calendar, Clock, Hash, Zap } from "lucide-react"
import type { RunOverview, EventItem, GraphNode } from "../../types"
import { formatDuration, formatWhen } from "../../lib/utils"
import {
  decisionKindLabel,
  eventTitle,
  outcomeLabel,
  statusLabel,
  tokensLabel,
  truncate,
} from "../../lib/humanize"
import { JsonViewer } from "../JsonViewer"

interface InspectorProps {
  overview: RunOverview | null
  selectedEvent: EventItem | null
  selectedGraphNode?: GraphNode | null
  /** Every event of the open run, to resolve what a graph node or decision refers to. */
  events?: EventItem[]
  /** A run is being loaded: say so instead of inviting to select one. */
  isLoading?: boolean
  onSelectEvent?: (event: EventItem) => void
}

export function Inspector({ overview, selectedEvent, selectedGraphNode, events = [], isLoading = false, onSelectEvent }: InspectorProps) {
  return (
    <aside className="w-[340px] min-w-[340px] border-l border-line bg-surface-strong flex flex-col shrink-0 overflow-hidden">
      <div className="px-4 py-2 border-b border-line flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">Inspector</span>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {selectedGraphNode ? (
          <GraphNodeInspector node={selectedGraphNode} events={events} onSelectEvent={onSelectEvent} />
        ) : selectedEvent ? (
          <EventInspector event={selectedEvent} />
        ) : overview ? (
          <RunInspector overview={overview} />
        ) : (
          <p className="text-xs text-muted text-center py-8">
            {isLoading ? "Loading run..." : "Select a run, event, or graph node to inspect."}
          </p>
        )}
      </div>
    </aside>
  )
}

function GraphNodeInspector({
  node,
  events,
  onSelectEvent,
}: {
  node: GraphNode
  events: EventItem[]
  onSelectEvent?: (event: EventItem) => void
}) {
  const technical = (
    <TechnicalDetails>
      <Row label="ID" value={node.id} />
      <Row label="Type" value={node.type} />
      <Row label="Position" value={`${Math.round(node.position.x)}, ${Math.round(node.position.y)}`} />
      {node.data && Object.keys(node.data).length > 0 && <JsonViewer value={node.data} maxHeight="200px" />}
    </TechnicalDetails>
  )

  if (node.type === "event") {
    const event = events.find((item) => item.id === node.data?.eventId)
    if (event) return <EventInspector event={event} />
  }

  if (node.type === "decision") {
    const kind = String(node.data?.kind ?? "")
    const evidenceIds = Array.isArray(node.data?.evidenceIds) ? (node.data.evidenceIds as number[]) : []
    const evidence = evidenceIds
      .map((id) => events.find((item) => item.id === id))
      .filter((item): item is EventItem => item !== undefined)
    return (
      <div className="space-y-4">
        <div>
          <Badge tone="warning">{decisionKindLabel(kind)}</Badge>
          <p className="text-sm font-medium mt-2">{node.label}</p>
          {typeof node.data?.summary === "string" && <p className="text-xs text-muted mt-1">{node.data.summary}</p>}
        </div>

        <div className="space-y-1 text-xs">
          <Row label="Outcome" value={outcomeLabel(node.data?.outcome as string | null)} />
        </div>

        {evidence.length > 0 && (
          <div className="space-y-1">
            <SectionTitle>What this is based on</SectionTitle>
            <ul className="space-y-1">
              {evidence.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onSelectEvent?.(item)}
                    className="w-full text-left text-xs rounded border border-line bg-surface px-2 py-1.5 hover:bg-surface-strong transition-colors"
                  >
                    <span className="font-medium">{eventTitle(item.type)}</span>
                    {item.tool_name && <span className="text-muted"> · {item.tool_name}</span>}
                    <span className="block text-muted truncate">{item.summary}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {technical}
      </div>
    )
  }

  // Artifacts, and anything else: what it is and what it says.
  const kind = typeof node.data?.kind === "string" ? node.data.kind : null
  return (
    <div className="space-y-4">
      <div>
        <Badge tone="info">{kind ? kind : node.type === "artifact" ? "Artifact" : eventTitle(node.type)}</Badge>
        <p className="text-sm font-medium mt-2">{node.label}</p>
        {typeof node.data?.summary === "string" && <p className="text-xs text-muted mt-1">{node.data.summary}</p>}
      </div>
      {technical}
    </div>
  )
}

function RunInspector({ overview }: { overview: RunOverview }) {
  const tokens = overview.execution.token_usage?.total_tokens ?? 0
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
        <SectionTitle>Execution</SectionTitle>
        <div className="space-y-1 text-xs">
          <Row label="Status" value={statusLabel(overview.status)} />
          <Row label="Provider" value={overview.provider ?? "—"} />
          <Row label="Model" value={overview.model ?? "—"} />
          <Row label="Turns" value={overview.execution.model_turn_count} />
          {tokens > 0 && <Row label="Tokens" value={tokens.toLocaleString()} />}
          {overview.retry_count > 0 && <Row label="Retries" value={overview.retry_count} />}
          <Row label="Commands" value={overview.execution.command_count} />
        </div>
      </div>

      {overview.flags.length > 0 && (
        <div className="space-y-1">
          <SectionTitle>Flags</SectionTitle>
          <div className="flex flex-wrap gap-1">
            {overview.flags.map((f, i) => (
              <span
                key={i}
                title={f.label}
                className={`text-[10px] px-1.5 py-0.5 rounded border ${
                  f.type === "error" ? "border-danger/30 text-danger bg-danger/10" :
                  f.type === "warning" ? "border-warning/30 text-warning bg-warning/10" :
                  "border-info/30 text-info bg-info/10"
                }`}
              >
                {truncate(f.label, 140)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function EventInspector({ event }: { event: EventItem }) {
  const failed = event.status === "failed"
  const tokens = tokensLabel(event)
  const requestedTools = Array.isArray(event.metadata?.requested_tools) ? (event.metadata.requested_tools as string[]) : []
  const agentName = typeof event.metadata?.agent_name === "string" ? event.metadata.agent_name : null
  const args = event.payload_full && typeof event.payload_full === "object" ? (event.payload_full as Record<string, unknown>).args : null
  const hasArgs = args !== null && typeof args === "object" && Object.keys(args as object).length > 0

  return (
    <div className="space-y-4">
      <div>
        <Badge tone={failed ? "danger" : "accent"}>{eventTitle(event.type)}</Badge>
        <p className={`text-sm mt-2 ${failed ? "text-danger" : ""}`}>{event.summary}</p>
        {failed && event.error_code && <p className="text-xs text-muted mt-1">Error: {event.error_code}</p>}
      </div>

      <div className="space-y-1 text-xs">
        <Row label="Result" value={statusLabel(event.status)} />
        {event.duration_ms !== null && <Row label="Duration" value={formatDuration(event.duration_ms)} />}
        <Row label="When" value={formatWhen(event.timestamp)} />
        {event.tool_name && <Row label="Tool" value={event.tool_name} />}
        {agentName && <Row label="Agent" value={agentName} />}
        {event.model && <Row label="Model" value={event.model} />}
        {event.provider && <Row label="Provider" value={event.provider} />}
        {tokens && <Row label="Tokens" value={tokens} />}
        {requestedTools.length > 0 && <Row label="Asked for" value={requestedTools.join(", ")} />}
      </div>

      {hasArgs && (
        <div className="space-y-1">
          <SectionTitle>Arguments</SectionTitle>
          <JsonViewer value={args as Record<string, unknown>} maxHeight="160px" />
        </div>
      )}

      <TechnicalDetails>
        <Row label="Source" value={event.actor} />
        <Row label="Step ID" value={event.step_id ?? "—"} />
        <Row label="Parent step" value={event.parent_step_id ?? "—"} />
        {event.metadata && Object.keys(event.metadata).length > 0 && (
          <>
            <SectionTitle>Metadata</SectionTitle>
            <JsonViewer value={event.metadata} maxHeight="160px" />
          </>
        )}
        {event.payload_full && (
          <>
            <SectionTitle>Payload</SectionTitle>
            <JsonViewer value={event.payload_full} maxHeight="240px" />
          </>
        )}
      </TechnicalDetails>
    </div>
  )
}

function Badge({ tone, children }: { tone: "accent" | "warning" | "danger" | "info"; children: React.ReactNode }) {
  const tones = {
    accent: "bg-accent/10 text-accent border-accent/20",
    warning: "bg-warning/10 text-warning border-warning/20",
    danger: "bg-danger/10 text-danger border-danger/20",
    info: "bg-info/10 text-info border-info/20",
  }
  return <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded border ${tones[tone]}`}>{children}</span>
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{children}</p>
}

/** The identifiers and raw data that help when debugging, folded away: they are not what most people look for. */
function TechnicalDetails({ children }: { children: React.ReactNode }) {
  return (
    <details className="text-xs group">
      <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-muted hover:text-text select-none">
        Technical details
      </summary>
      <div className="mt-2 space-y-1">{children}</div>
    </details>
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
    <div className="flex justify-between gap-3 py-0.5 border-b border-line/50">
      <span className="text-muted shrink-0">{label}</span>
      <span className="font-medium truncate max-w-[200px]" title={typeof value === "string" ? value : undefined}>{value}</span>
    </div>
  )
}
