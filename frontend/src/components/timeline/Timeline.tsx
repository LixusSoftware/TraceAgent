import { useMemo, useState } from "react"
import { ChevronDown, ChevronRight, Clock, AlertCircle, CheckCircle2, Loader2 } from "lucide-react"
import type { TimelineResponse, EventItem, TimelineGroup } from "../../types"
import { EventIcon } from "./EventIcon"
import { formatDuration, formatWhen } from "../../lib/utils"

interface TimelineProps {
  timeline: TimelineResponse | null
  selectedEvent: EventItem | null
  onSelectEvent: (event: EventItem | null) => void
  isLoading: boolean
}

export function Timeline({ timeline, selectedEvent, onSelectEvent, isLoading }: TimelineProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set())

  const tree = useMemo(() => {
    if (!timeline) return []
    const byParent = new Map<string | null, TimelineGroup[]>()
    for (const group of timeline.groups) {
      const key = group.parent_step_id ?? null
      if (!byParent.has(key)) byParent.set(key, [])
      byParent.get(key)!.push(group)
    }
    return byParent.get(null) ?? []
  }, [timeline])

  const totalDuration = useMemo(() => {
    if (!timeline || timeline.groups.length === 0) return 0
    let maxEnd = 0
    for (const g of timeline.groups) {
      if (g.duration_ms !== null) maxEnd = Math.max(maxEnd, g.duration_ms)
    }
    return maxEnd
  }, [timeline])

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev)
      if (next.has(stepId)) next.delete(stepId)
      else next.add(stepId)
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted text-sm">
        Loading timeline...
      </div>
    )
  }

  if (!timeline || timeline.groups.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted text-sm">
        No timeline data available.
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      {/* Timeline header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">
          Events
        </h3>
        <span className="text-[10px] text-muted">
          {timeline.groups.reduce((s, g) => s + g.events.length, 0)} events · {formatDuration(totalDuration)}
        </span>
      </div>

      <div className="space-y-0.5">
        {tree.map((group) => (
          <TimelineGroupNode
            key={group.step_id}
            group={group}
            depth={0}
            expandedSteps={expandedSteps}
            onToggle={toggleStep}
            selectedEvent={selectedEvent}
            onSelectEvent={onSelectEvent}
            totalDuration={totalDuration}
          />
        ))}
      </div>
    </div>
  )
}

function TimelineGroupNode({
  group,
  depth,
  expandedSteps,
  onToggle,
  selectedEvent,
  onSelectEvent,
  totalDuration,
}: {
  group: TimelineGroup
  depth: number
  expandedSteps: Set<string>
  onToggle: (id: string) => void
  selectedEvent: EventItem | null
  onSelectEvent: (event: EventItem | null) => void
  totalDuration: number
}) {
  const isExpanded = expandedSteps.has(group.step_id)
  const hasChildren = group.events.length > 1 || group.event_count > group.events.length
  const pct = totalDuration > 0 && group.duration_ms !== null
    ? Math.max(2, (group.duration_ms / totalDuration) * 100)
    : 0

  const statusColor =
    group.status === "completed" ? "bg-accent" :
    group.status === "failed" ? "bg-danger" :
    group.status === "running" ? "bg-warning" :
    "bg-muted"

  return (
    <div>
      <button
        onClick={() => onToggle(group.step_id)}
        className="flex items-center gap-1.5 w-full text-left py-1.5 px-2 rounded hover:bg-surface-strong transition-colors group"
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        {hasChildren ? (
          isExpanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-muted shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-muted shrink-0" />
          )
        ) : (
          <span className="w-3.5 shrink-0" />
        )}
        <EventIcon type={group.events[0]?.type ?? "unknown"} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium truncate">{group.label}</span>
            <StatusBadge status={group.status} />
          </div>
          {pct > 0 && (
            <div className="flex items-center gap-2 mt-1">
              <div className="flex-1 h-1 bg-line rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${statusColor}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {group.duration_ms !== null && (
            <span className="text-[10px] text-muted flex items-center gap-0.5">
              <Clock className="w-3 h-3" />
              {formatDuration(group.duration_ms)}
            </span>
          )}
          <span className="text-[10px] text-muted bg-surface-strong px-1.5 py-0.5 rounded">
            {group.event_count} events
          </span>
        </div>
      </button>

      {isExpanded && (
        <div className="relative">
          {depth < 5 && (
            <div
              className="absolute top-0 bottom-0 w-px bg-line/50"
              style={{ left: `${depth * 16 + 18}px` }}
            />
          )}
          {group.events.map((event) => (
            <TimelineEventRow
              key={event.id}
              event={event}
              depth={depth + 1}
              isSelected={selectedEvent?.id === event.id}
              onSelect={() => onSelectEvent(event)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function TimelineEventRow({
  event,
  depth,
  isSelected,
  onSelect,
}: {
  event: EventItem
  depth: number
  isSelected: boolean
  onSelect: () => void
}) {
  return (
    <button
      onClick={onSelect}
      className={`flex items-center gap-2 w-full text-left py-1.5 px-2 rounded transition-colors ${
        isSelected ? "bg-accent/10" : "hover:bg-surface-strong"
      }`}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
    >
      <EventIcon type={event.type} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className={`text-xs truncate ${isSelected ? "text-accent font-medium" : "text-text"}`}>
            {event.summary}
          </p>
          {event.status && <StatusBadge status={event.status} />}
        </div>
        {event.tool_name && (
          <p className="text-[10px] text-muted truncate">{event.tool_name}</p>
        )}
      </div>
      <div className="flex items-center gap-3 shrink-0">
        {event.duration_ms !== null && (
          <span className="text-[10px] text-muted flex items-center gap-0.5">
            <Clock className="w-3 h-3" />
            {formatDuration(event.duration_ms)}
          </span>
        )}
        <span className="text-[10px] text-muted w-14 text-right">{formatWhen(event.timestamp)}</span>
      </div>
    </button>
  )
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
    completed: { icon: CheckCircle2, color: "text-accent bg-accent/10 border-accent/20", label: "ok" },
    succeeded: { icon: CheckCircle2, color: "text-accent bg-accent/10 border-accent/20", label: "ok" },
    failed: { icon: AlertCircle, color: "text-danger bg-danger/10 border-danger/20", label: "err" },
    running: { icon: Loader2, color: "text-warning bg-warning/10 border-warning/20", label: "run" },
    requested: { icon: CheckCircle2, color: "text-info bg-info/10 border-info/20", label: "req" },
  }

  const c = config[status] ?? { icon: CheckCircle2, color: "text-muted bg-surface-strong border-line", label: status.slice(0, 3) }
  const Icon = c.icon

  return (
    <span className={`inline-flex items-center gap-0.5 text-[9px] px-1 py-0 rounded border font-medium ${c.color}`}>
      <Icon className="w-2.5 h-2.5" />
      {c.label}
    </span>
  )
}
