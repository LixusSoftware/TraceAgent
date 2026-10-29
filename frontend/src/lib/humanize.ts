import type { EventItem, TimelineGroup } from "../types"

// The server speaks in machine names ("llm.completed", "tool_choice"). People read these instead.

const EVENT_TITLES: Record<string, string> = {
  "run.started": "Run started",
  "run.completed": "Run finished",
  "run.failed": "Run failed",
  "chain.started": "Agent started",
  "chain.completed": "Agent finished",
  "chain.failed": "Agent failed",
  "llm.started": "Model request",
  "llm.completed": "Model response",
  "llm.failed": "Model call failed",
  "model.requested": "Model request",
  "model.responded": "Model response",
  "tool.requested": "Tool requested",
  "tool.started": "Tool started",
  "tool.succeeded": "Tool finished",
  "tool.failed": "Tool failed",
  "retriever.queried": "Search started",
  "retriever.responded": "Search finished",
  "retriever.failed": "Search failed",
  "agent.action": "Agent step",
  "agent.finish": "Agent step finished",
  "agent.failed": "Agent step failed",
  "command.started": "Command started",
  "command.succeeded": "Command finished",
  "command.failed": "Command failed",
  "file.read": "File read",
  "file.written": "File changed",
  "patch.applied": "Patch applied",
  "artifact.created": "Artifact created",
}

const GROUP_TITLES: Record<string, string> = {
  chain: "Agent run",
  llm: "Model call",
  model: "Model call",
  agent: "Agent step",
  retriever: "Search",
}

const DECISION_KINDS: Record<string, string> = {
  tool_choice: "Tool choice",
  retry: "Retry",
  recovery: "Recovery",
  completion: "Completion",
  termination: "Termination",
  command: "Command",
}

const OUTCOMES: Record<string, string> = {
  requested: "Requested",
  retry: "Retried",
  succeeded: "Succeeded",
  failed: "Failed",
  started: "Started",
  completed: "Completed",
  running: "Running",
  created: "Created",
}

function sentence(text: string): string {
  const spaced = text.replace(/[._]/g, " ").trim()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function eventTitle(type: string): string {
  return EVENT_TITLES[type] ?? sentence(type)
}

export function decisionKindLabel(kind: string): string {
  return DECISION_KINDS[kind] ?? sentence(kind)
}

export function outcomeLabel(outcome: string | null | undefined): string {
  if (!outcome) return "—"
  return OUTCOMES[outcome] ?? sentence(outcome)
}

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "—"
  return OUTCOMES[status] ?? sentence(status)
}

/** Title of a timeline group: the tool name, a command or file path, or what kind of step it is. */
export function groupTitle(group: TimelineGroup): string {
  if (group.tool_name) return group.label
  const first = group.events[0]
  const kind = first?.type.split(".")[0] ?? ""
  if (kind === "run") return eventTitle(group.events[group.events.length - 1].type)
  if (kind === "command") return commandTitle(group.label)
  const title = GROUP_TITLES[kind]
  if (!title) return group.label
  const detail = kind === "chain" ? first.metadata?.agent_name : first.model
  return typeof detail === "string" && detail ? `${title} · ${detail}` : title
}

/** Label of an execution-graph event node: what happened, and to which tool. */
export function eventNodeLabel(type: string, toolName: unknown): string {
  const title = eventTitle(type)
  return typeof toolName === "string" && toolName ? `${title} · ${toolName}` : title
}

export function tokensLabel(event: EventItem): string | null {
  const prompt = event.metadata?.prompt_tokens
  const completion = event.metadata?.completion_tokens
  if (typeof prompt !== "number" && typeof completion !== "number") return null
  return `${prompt ?? 0} in · ${completion ?? 0} out`
}

/** Collapse whitespace and cut a long text, so it fits one row. */
export function truncate(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim()
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat
}

/**
 * Short title of a command step, not the whole program: the first comment of a script says what the step
 * does; without one, the first line that is not an import.
 */
export function commandTitle(command: string, max = 72): string {
  const code = command.replace(/^\s*(?:python3?|py)\s+-c\s+/, "")
  const lines = code.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  const comment = lines.find((line) => line.startsWith("#"))?.replace(/^#+\s*/, "")
  const firstCode = lines.find((line) => !line.startsWith("#") && !/^(?:import|from)\s/.test(line))
  return truncate(comment || firstCode || lines[0] || code, max)
}

function formatValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value)
}

/** The arguments of a tool call as `name=value, other=value`, for the timeline row. */
export function argsSummary(group: TimelineGroup, max = 90): string | null {
  const started = group.events.find((event) => event.type === "tool.started")
  if (!started) return null

  let args: unknown = (started.payload_full as { args?: unknown } | null)?.args
  if (args === undefined && typeof started.metadata?.args_summary === "string") {
    try {
      args = JSON.parse(started.metadata.args_summary)
    } catch {
      return truncate(started.metadata.args_summary.replace(/^[{\s]+|[}\s]+$/g, ""), max) || null
    }
  }
  if (!args || typeof args !== "object" || Object.keys(args as object).length === 0) return null
  const text = Object.entries(args as Record<string, unknown>)
    .map(([key, value]) => `${key}=${formatValue(value)}`)
    .join(", ")
  return truncate(text, max)
}
