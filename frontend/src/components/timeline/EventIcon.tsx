import {
  Flag,
  ArrowUp,
  ArrowDown,
  Zap,
  MessageSquare,
  Wrench,
  FileText,
  Bot,
  Terminal,
  Folder,
  Package,
  Pencil,
  CircleHelp,
} from "lucide-react"

const iconMap: Record<string, typeof Flag> = {
  "run.started": Flag,
  "run.completed": Flag,
  "run.failed": Flag,
  "model.requested": ArrowUp,
  "model.responded": ArrowDown,
  "chain.started": Zap,
  "chain.completed": Zap,
  "chain.failed": Zap,
  "llm.started": MessageSquare,
  "llm.completed": MessageSquare,
  "llm.failed": MessageSquare,
  "tool.started": Wrench,
  "tool.succeeded": Wrench,
  "tool.failed": Wrench,
  "retriever.queried": FileText,
  "retriever.responded": FileText,
  "agent.action": Bot,
  "agent.finish": Bot,
  "command.started": Terminal,
  "command.succeeded": Terminal,
  "command.failed": Terminal,
  "file.read": Folder,
  "file.written": Folder,
  "artifact.created": Package,
  "patch.applied": Pencil,
}

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

export function EventIcon({ type }: { type: string }) {
  const Icon = iconMap[type] ?? CircleHelp
  const colorClass = colorMap[type] ?? "text-muted"
  return <Icon className={`w-4 h-4 shrink-0 ${colorClass}`} />
}

export function getEventColor(type: string): string {
  return colorMap[type] ?? "text-muted"
}
