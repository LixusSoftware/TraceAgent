import { useState } from "react"
import { Calendar, Clock, Hash, Zap } from "lucide-react"
import type { RunOverview, EventItem, GraphNode } from "../../types"
import { formatDuration, formatWhen } from "../../lib/utils"
import {
  decisionKindLabel,
  describeMessages,
  eventTitle,
  FINISH_EVENTS,
  outcomeLabel,
  statusLabel,
  stepCounts,
  tokensLabel,
  truncate,
  type MessageView,
} from "../../lib/humanize"
import { CopyButton, JsonViewer } from "../JsonViewer"

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
          <EventInspector event={selectedEvent} events={events} />
        ) : overview ? (
          <RunInspector overview={overview} events={events} />
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
    if (event) return <EventInspector event={event} events={events} />
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

/** An object of plain values, one of which is a text of several lines (a traceback, a script). */
function hasMultilineText(value: unknown): value is Record<string, string | number | boolean | null> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false
  const values = Object.values(value as Record<string, unknown>)
  const plain = values.every((item) => item === null || ["string", "number", "boolean"].includes(typeof item))
  return plain && values.some((item) => typeof item === "string" && item.includes("\n"))
}

/** A value to read: a text as text, anything else as formatted JSON, both copiable. */
function ValueBlock({ value, maxHeight = "240px" }: { value: unknown; maxHeight?: string }) {
  if (typeof value === "string") {
    return (
      <div className="relative rounded border border-line bg-bg p-2">
        <div className="absolute top-1 right-1"><CopyButton text={value} label="Copy" /></div>
        <p className="text-xs whitespace-pre-wrap break-words overflow-auto pr-6" style={{ maxHeight }}>{value}</p>
      </div>
    )
  }
  // JSON would show the line breaks of a traceback as \n: with a text of several lines, each key is shown with its
  // text as it is, line breaks included.
  if (hasMultilineText(value)) {
    return (
      <div className="relative rounded border border-line bg-bg p-2 space-y-2">
        <div className="absolute top-1 right-1"><CopyButton text={JSON.stringify(value, null, 2)} label="Copy as JSON" /></div>
        {Object.entries(value).map(([key, item]) => (
          <div key={key}>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted pr-6">{key}</p>
            <p className="text-xs font-mono whitespace-pre-wrap break-words">{String(item)}</p>
          </div>
        ))}
      </div>
    )
  }
  return <JsonViewer value={value} maxHeight={maxHeight} />
}

/** What the agent answered, whole when the server kept it, else its summary: the first thing to read in a run. */
function FinalOutput({ overview, events }: { overview: RunOverview; events: EventItem[] }) {
  const ended = [...events].reverse().find((event) => event.type === "run.completed")
  const whole = (ended?.payload_full as { final_output?: unknown } | null | undefined)?.final_output
  const text = overview.final_output_summary
  if (whole === undefined && !text) return null
  const failed = overview.status === "failed"
  return (
    <div className="space-y-1">
      <SectionTitle>{failed ? "Why it failed" : "Final output"}</SectionTitle>
      <ValueBlock value={whole !== undefined ? whole : text} maxHeight="280px" />
    </div>
  )
}

function RunInspector({ overview, events }: { overview: RunOverview; events: EventItem[] }) {
  const tokens = overview.execution.token_usage?.total_tokens ?? 0
  const { steps, nested } = stepCounts(events, overview.tool_count, overview.execution.command_count)
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold mb-1">{overview.agent_name}</h3>
        <p className="text-xs text-muted">{overview.goal}</p>
      </div>

      <FinalOutput overview={overview} events={events} />

      <div className="grid grid-cols-2 gap-2">
        <Stat
          icon={Hash}
          label="Steps"
          value={steps}
          title={`${overview.tool_count} tool calls, ${overview.execution.command_count} commands${nested > 0 ? ` (${nested} of them inside tools, not counted twice)` : ""}`}
        />
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
          <Row label="Model calls" value={overview.execution.model_turn_count} />
          {tokens > 0 && <Row label="Tokens" value={tokens.toLocaleString()} />}
          {overview.retry_count > 0 && <Row label="Retries" value={overview.retry_count} />}
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

// Metadata keys the event inspector already presents (as rows, sections or the title), or that are internal bookkeeping.
const SHOWN_ABOVE = new Set([
  "provider", "model", "prompt_tokens", "completion_tokens", "total_tokens", "requests", "tool_calls", "requested_tools",
  "agent_name", "message_count", "run_step", "finish_reason", "finish_reasons", "call_id", "tool_name", "args_summary",
  "output_summary", "output_hash", "prompt_summary", "agent_call_id", "conversation_id", "pydantic_run_id",
])

/** A text that is JSON shows as JSON; anything else stays a text. */
function parseMaybe(value: unknown): unknown {
  if (typeof value !== "string") return value
  try {
    const parsed = JSON.parse(value)
    return parsed !== null && typeof parsed === "object" ? parsed : value
  } catch {
    return value
  }
}

/** An internal identifier: kept for debugging, with a button to copy it. */
function IdRow({ label, value }: { label: string; value: string | null }) {
  if (!value) return <Row label={label} value="—" />
  return (
    <div className="flex items-center justify-between gap-2 py-0.5 border-b border-line/50">
      <span className="text-muted shrink-0">{label}</span>
      <span className="flex items-center gap-1 min-w-0">
        <span className="font-mono text-[11px] truncate" title={value}>{value}</span>
        <CopyButton text={value} label={`Copy ${label}`} />
      </span>
    </div>
  )
}

function argsOf(event: EventItem | undefined): unknown {
  return event?.payload_full && typeof event.payload_full === "object" ? (event.payload_full as Record<string, unknown>).args : null
}

function EventInspector({ event, events = [] }: { event: EventItem; events?: EventItem[] }) {
  const failed = event.status === "failed"
  const tokens = tokensLabel(event)
  const requestedTools = Array.isArray(event.metadata?.requested_tools) ? (event.metadata.requested_tools as string[]) : []
  const agentName = typeof event.metadata?.agent_name === "string" ? event.metadata.agent_name : null
  // The arguments live in the event that started the tool, which the timeline no longer lists as a row of its own.
  const started = events.find((other) => other.step_id === event.step_id && other.type === "tool.started")
  const args = argsOf(event) ?? argsOf(started)
  const hasArgs = args !== null && typeof args === "object" && Object.keys(args as object).length > 0
  const isModelCall = event.type.startsWith("llm.")
  // A "started" event is only the beginning: in a run that has ended it must not say "Running".
  const finishTypes = FINISH_EVENTS[event.type]
  const finish = finishTypes ? events.find((other) => other.step_id === event.step_id && finishTypes.includes(other.type)) : undefined
  const status = (finish ?? event).status
  // What an agent answered, as it came with the end of its run.
  const agentOutput = event.type === "chain.completed" && typeof event.metadata?.output_summary === "string" ? parseMaybe(event.metadata.output_summary) : undefined
  const payload = (event.payload_full ?? {}) as Record<string, unknown>
  // What a finished tool returned: the whole output when it was kept, else its summary.
  const result = event.type === "tool.succeeded" ? (payload.output !== undefined ? payload.output : parseMaybe(payload.output_summary)) : undefined
  const finalOutput = event.type === "run.completed" ? payload.final_output : undefined
  // The metadata the inspector already shows above would only repeat itself.
  const leftover = Object.fromEntries(Object.entries(event.metadata ?? {}).filter(([key, value]) => !SHOWN_ABOVE.has(key) && value !== null && value !== undefined))

  return (
    <div className="space-y-4">
      <div>
        <Badge tone={failed ? "danger" : "accent"}>{eventTitle(event.type)}</Badge>
        <p className={`text-sm mt-2 ${failed ? "text-danger" : ""}`}>{event.summary}</p>
        {failed && event.error_code && <p className="text-xs text-muted mt-1">Error: {event.error_code}</p>}
      </div>

      <div className="space-y-1 text-xs">
        <Row label="Status" value={statusLabel(status)} />
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

      {result !== undefined && (
        <div className="space-y-1">
          <SectionTitle>Result</SectionTitle>
          <ValueBlock value={result} />
        </div>
      )}

      {agentOutput !== undefined && (
        <div className="space-y-1">
          <SectionTitle>Agent output</SectionTitle>
          <ValueBlock value={agentOutput} />
        </div>
      )}

      {finalOutput !== undefined && (
        <div className="space-y-1">
          <SectionTitle>Final output</SectionTitle>
          <ValueBlock value={finalOutput} maxHeight="280px" />
        </div>
      )}

      {isModelCall && <ModelContent event={event} />}

      <TechnicalDetails>
        <Row label="Source" value={event.actor} />
        <IdRow label="Step ID" value={event.step_id} />
        <IdRow label="Parent step" value={event.parent_step_id} />
        {Object.keys(leftover).length > 0 && (
          <>
            <SectionTitle>Other metadata</SectionTitle>
            <JsonViewer value={leftover} maxHeight="160px" />
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

/** What a model call was asked and what it answered: the thing to read to understand a decision. */
function ModelContent({ event }: { event: EventItem }) {
  const payload = (event.payload_full ?? {}) as Record<string, unknown>
  const prompt = describeMessages(payload.input_messages)
  const response = describeMessages(payload.output_messages)

  if (prompt.length === 0 && response.length === 0) {
    // Only the finished call carries the content: say why it is missing instead of staying silent.
    if (event.type !== "llm.completed") return null
    return (
      <div className="space-y-1">
        <SectionTitle>Prompt and response</SectionTitle>
        <p className="text-xs text-muted">
          Not captured. The agent sends them unless it turns that off (<code className="font-mono">capture_content=False</code>
          {" "}or no content in OpenTelemetry), and the server keeps them only while{" "}
          <code className="font-mono">TRACE_AGENT_CAPTURE_FULL_PAYLOADS</code> is on.
        </p>
      </div>
    )
  }

  return (
    <>
      {prompt.length > 0 && (
        <div className="space-y-1">
          <SectionTitle>Prompt</SectionTitle>
          <MessageList messages={prompt} />
        </div>
      )}
      {response.length > 0 && (
        <div className="space-y-1">
          <SectionTitle>Response</SectionTitle>
          <MessageList messages={response} />
        </div>
      )}
    </>
  )
}

const LONG_MESSAGE = 700

function MessageList({ messages }: { messages: MessageView[] }) {
  return (
    <ul className="space-y-1.5">
      {messages.map((message, index) => (
        <li key={index} className="rounded border border-line bg-surface px-2 py-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{message.label}</p>
          <MessageText text={message.text} />
        </li>
      ))}
    </ul>
  )
}

/** A long message (a system prompt, a file) is shortened with a button to read it whole: an inner scroll box would trap the wheel. */
function MessageText({ text }: { text: string }) {
  const [whole, setWhole] = useState(false)
  const long = text.length > LONG_MESSAGE
  return (
    <>
      <p className="text-xs whitespace-pre-wrap break-words">{long && !whole ? `${text.slice(0, LONG_MESSAGE)}…` : text}</p>
      {long && (
        <button type="button" onClick={() => setWhole((value) => !value)} className="mt-1 text-[10px] text-accent hover:underline">
          {whole ? "Show less" : `Show all (${text.length.toLocaleString("en-GB")} characters)`}
        </button>
      )}
    </>
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

function Stat({ icon: Icon, label, value, title }: { icon: typeof Hash; label: string; value: React.ReactNode; title?: string }) {
  return (
    <div className="bg-surface border border-line rounded-md p-2" title={title}>
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
      <span className="font-medium text-right break-words max-w-[200px]" title={typeof value === "string" ? value : undefined}>{value}</span>
    </div>
  )
}
