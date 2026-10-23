const colorMap: Record<string, string> = {
  "run.started": "text-accent",
  "run.completed": "text-accent",
  "run.failed": "text-danger",
  "model.requested": "text-info",
  "model.responded": "text-accent",
  "chain.started": "text-warning",
  "chain.completed": "text-warning",
  "chain.failed": "text-danger",
  "llm.started": "text-info",
  "llm.completed": "text-accent",
  "llm.failed": "text-danger",
  "tool.started": "text-muted",
  "tool.succeeded": "text-accent",
  "tool.failed": "text-danger",
  "retriever.queried": "text-muted",
  "retriever.responded": "text-muted",
  "agent.action": "text-warning",
  "agent.finish": "text-accent",
  "command.started": "text-muted",
  "command.succeeded": "text-accent",
  "command.failed": "text-danger",
  "file.read": "text-muted",
  "file.written": "text-accent",
  "artifact.created": "text-accent",
  "patch.applied": "text-warning",
}

export function getEventColor(type: string): string {
  return colorMap[type] ?? "text-muted"
}
