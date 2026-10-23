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
