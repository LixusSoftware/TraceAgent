import { useMemo, useState } from "react"
import { ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown, Clock, AlertCircle, CheckCircle2, Loader2 } from "lucide-react"
import type { TimelineResponse, EventItem, TimelineGroup } from "../../types"
import { EventIcon } from "./EventIcon"
import { formatDuration, formatWhen } from "../../lib/utils"
import { argsSummary, eventTitle, groupTitle, resultSummary } from "../../lib/humanize"

type TimelineRow = { seq: number; event: EventItem } | { seq: number; child: TimelineGroup }

/** A group has something to open when it holds several events or has child groups. */
function hasNested(group: TimelineGroup, childrenByParent: Map<string, TimelineGroup[]>): boolean {
  return group.events.length > 1 || group.event_count > group.events.length || childrenByParent.has(group.step_id)
}

const FINISHES: Record<string, string[]> = {
  "tool.started": ["tool.succeeded", "tool.failed"],
  "command.started": ["command.succeeded", "command.failed"],
  "chain.started": ["chain.completed", "chain.failed"],
}

/** "Started <tool>." says nothing the step's own row does not say, once the step has a result row. */
function isRedundantStart(group: TimelineGroup, event: EventItem): boolean {
  const finishes = FINISHES[event.type]
  return !!finishes && group.events.some((other) => finishes.includes(other.type))
}

/** The end of an agent says what it answered; "Pydantic AI run 'agent' completed" says nothing the row does not. */
function rowText(event: EventItem): string {
  const answer = event.metadata?.output_summary
  return event.type === "chain.completed" && typeof answer === "string" && answer ? answer : event.summary
}

interface TimelineProps {
  timeline: TimelineResponse | null
  selectedEvent: EventItem | null
  onSelectEvent: (event: EventItem | null) => void
  isLoading: boolean
}

export function Timeline({ timeline, selectedEvent, onSelectEvent, isLoading }: TimelineProps) {
  // What the person expanded or collapsed, kept with the run it was for. Until they touch anything the
  // first level is open, so the model calls and tools of a run are visible without a click.
  const [choice, setChoice] = useState<{ runId: string; expanded: Set<string> } | null>(null)

  const { roots, childrenByParent } = useMemo(() => {
    const roots: TimelineGroup[] = []
    const childrenByParent = new Map<string, TimelineGroup[]>()
    if (!timeline) return { roots, childrenByParent }
    const known = new Set(timeline.groups.map((group) => group.step_id))
    for (const group of timeline.groups) {
      const parent = group.parent_step_id
      // A group whose parent is not in the timeline is shown at the top level, never dropped.
      if (parent && parent !== group.step_id && known.has(parent)) {
        const siblings = childrenByParent.get(parent) ?? []
        siblings.push(group)
        childrenByParent.set(parent, siblings)
      } else {
        roots.push(group)
      }
    }
    return { roots, childrenByParent }
  }, [timeline])

  const totalDuration = useMemo(() => {
    if (!timeline || timeline.groups.length === 0) return 0
    let maxEnd = 0
    for (const g of timeline.groups) {
      if (g.duration_ms !== null) maxEnd = Math.max(maxEnd, g.duration_ms)
    }
    return maxEnd
  }, [timeline])

  const expandable = useMemo(
    () => (timeline?.groups ?? []).filter((group) => hasNested(group, childrenByParent)).map((group) => group.step_id),
    [timeline, childrenByParent],
  )
  const defaultOpen = useMemo(
    () => new Set(roots.filter((group) => hasNested(group, childrenByParent)).map((group) => group.step_id)),
    [roots, childrenByParent],
  )
  const runId = timeline?.run_id ?? ""
  const expandedSteps = choice && choice.runId === runId ? choice.expanded : defaultOpen

  const toggleStep = (stepId: string) => {
    const next = new Set(expandedSteps)
    if (next.has(stepId)) next.delete(stepId)
    else next.add(stepId)
    setChoice({ runId, expanded: next })
  }
  const expandAll = () => setChoice({ runId, expanded: new Set(expandable) })
  const collapseAll = () => setChoice({ runId, expanded: new Set() })

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
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={expandAll}
            aria-label="Expand all steps"
            title="Expand all steps"
            className="flex items-center gap-1 text-[10px] text-muted hover:text-text transition-colors"
          >
            <ChevronsUpDown className="w-3 h-3" aria-hidden="true" />
            Expand all
          </button>
          <button
            type="button"
            onClick={collapseAll}
            aria-label="Collapse all steps"
            title="Collapse all steps"
            className="flex items-center gap-1 text-[10px] text-muted hover:text-text transition-colors"
          >
            <ChevronsDownUp className="w-3 h-3" aria-hidden="true" />
            Collapse all
          </button>
          <span className="text-[10px] text-muted">
            {timeline.groups.reduce((s, g) => s + g.events.length, 0)} events · {formatDuration(totalDuration)}
          </span>
        </div>
      </div>

      <div className="space-y-0.5">
        {roots.map((group) => (
          <TimelineGroupNode
            key={group.step_id}
            group={group}
            childrenByParent={childrenByParent}
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
  childrenByParent,
  depth,
  expandedSteps,
  onToggle,
  selectedEvent,
  onSelectEvent,
  totalDuration,
}: {
  group: TimelineGroup
  childrenByParent: Map<string, TimelineGroup[]>
  depth: number
  expandedSteps: Set<string>
  onToggle: (id: string) => void
  selectedEvent: EventItem | null
  onSelectEvent: (event: EventItem | null) => void
  totalDuration: number
}) {
  const isExpanded = expandedSteps.has(group.step_id)
  const childGroups = childrenByParent.get(group.step_id) ?? []
  const hasChildren = hasNested(group, childrenByParent)
  const title = groupTitle(group)
  const args = argsSummary(group)
  const result = resultSummary(group)
  // Own events and child groups interleaved in the order they happened.
  const rows: TimelineRow[] = [
    ...group.events
      .filter((event) => !isRedundantStart(group, event))
      .map((event): TimelineRow => ({ seq: event.seq, event })),
    ...childGroups.map((child): TimelineRow => ({ seq: child.events[0]?.seq ?? 0, child })),
  ].sort((a, b) => a.seq - b.seq)
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
        type="button"
        onClick={() => onToggle(group.step_id)}
        aria-expanded={hasChildren ? isExpanded : undefined}
        aria-label={`${title}${args ? ` (${args})` : ""}${result ? `, result: ${result}` : ""}, ${group.event_count} events${hasChildren ? (isExpanded ? ", expanded" : ", collapsed") : ""}`}
        title={group.label !== title ? group.label : undefined}
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
            <span className="text-xs font-medium truncate">{title}</span>
            {/* "Run started" is only the beginning: how the run ended is shown by "Run finished" or "Run failed". */}
            {group.events[0]?.type !== "run.started" && <StatusBadge status={group.status} />}
          </div>
          {args && <p className="text-[10px] text-muted truncate font-mono">{args}</p>}
          {result && <p className="text-[10px] text-muted truncate font-mono">→ {result}</p>}
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
          {rows.map((row) =>
            "child" in row ? (
              <TimelineGroupNode
                key={row.child.step_id}
                group={row.child}
                childrenByParent={childrenByParent}
                depth={depth + 1}
                expandedSteps={expandedSteps}
                onToggle={onToggle}
                selectedEvent={selectedEvent}
                onSelectEvent={onSelectEvent}
                totalDuration={totalDuration}
              />
            ) : (
              <TimelineEventRow
                key={row.event.id}
                event={row.event}
                depth={depth + 1}
                isSelected={selectedEvent?.id === row.event.id}
                onSelect={() => onSelectEvent(row.event)}
              />
            ),
          )}
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
      type="button"
      onClick={onSelect}
      aria-pressed={isSelected}
      aria-label={`${eventTitle(event.type)}: ${rowText(event)}`}
      className={`flex items-center gap-2 w-full text-left py-1.5 px-2 rounded transition-colors ${
        isSelected ? "bg-accent/10" : "hover:bg-surface-strong"
      }`}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
    >
      <EventIcon type={event.type} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className={`text-xs truncate ${isSelected ? "text-accent font-medium" : "text-text"}`}>
            {rowText(event)}
          </p>
          {/* A "started" event has not finished: its badge would contradict the result shown on the step. */}
          {event.status && !event.type.endsWith(".started") && <StatusBadge status={event.status} />}
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
