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
import { getEventColor } from "./eventColor"

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

export function EventIcon({ type }: { type: string }) {
  const Icon = iconMap[type] ?? CircleHelp
  return <Icon className={`w-4 h-4 shrink-0 ${getEventColor(type)}`} />
}
