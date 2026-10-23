import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Header } from "./components/layout/Header"
import { Sidebar } from "./components/layout/Sidebar"
import { Inspector } from "./components/layout/Inspector"
import { BottomPanel, type BottomTab } from "./components/layout/BottomPanel"
import { Timeline } from "./components/timeline/Timeline"
import { DashboardView } from "./components/dashboard/DashboardView"
import { CompareView } from "./components/compare/CompareView"
import { ExecutionGraph } from "./components/graph/ExecutionGraph"
import { api } from "./api"
import type { RunListItem, RunOverview, TimelineResponse, DashboardResponse, EventItem, GraphNode } from "./types"
import { useEventStream } from "./hooks/useEventStream"
import { GitBranch, List, Network } from "lucide-react"

type WorkspaceMode = "run" | "dashboard" | "compare"
type RunView = "timeline" | "graph" | "decisions"

export default function App() {
  const [runs, setRuns] = useState<RunListItem[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("run")
  const [loadedOverview, setOverview] = useState<RunOverview | null>(null)
  const [loadedTimeline, setTimeline] = useState<TimelineResponse | null>(null)
  const [loadedDashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [selection, setSelection] = useState<{ runId: string | null; event: EventItem | null; node: GraphNode | null }>({
    runId: null,
    event: null,
    node: null,
  })
  const [loadedRunId, setLoadedRunId] = useState<string | null>(null)
  const [, setError] = useState<string | null>(null)
  const [runViewMode, setRunViewMode] = useState<RunView>("timeline")
  const [bottomTab, setBottomTab] = useState<BottomTab>("audit")
  const [showSidebar, setShowSidebar] = useState(true)
  const [showBottomPanel, setShowBottomPanel] = useState(true)
  const [showInspector, setShowInspector] = useState(true)

  // Data of a run or view that is no longer selected is hidden by deriving it here,
  // instead of resetting state from inside effects.
  const overview = selectedRunId ? loadedOverview : null
  const timeline = selectedRunId ? loadedTimeline : null
  const dashboard = workspaceMode === "dashboard" ? loadedDashboard : null
  const isLoading = selectedRunId !== null && loadedRunId !== selectedRunId
  // The inspector only shows what was selected in the run that is open.
  const selectedEvent = selection.runId === selectedRunId ? selection.event : null
  const selectedGraphNode = selection.runId === selectedRunId ? selection.node : null

  const refreshRuns = useCallback(async () => {
    try {
      const data = await api.listRuns({})
      setRuns(data)
      setSelectedRunId((current) => {
        if (current && data.some((r) => r.id === current)) return current
        return data[0]?.id ?? null
      })
    } catch {
      setError("Failed to load runs")
    }
  }, [])

  useEffect(() => {
    const first = setTimeout(refreshRuns, 0)
    const id = setInterval(refreshRuns, 30000)
    return () => {
      clearTimeout(first)
      clearInterval(id)
    }
  }, [refreshRuns])

  useEffect(() => {
    if (!selectedRunId) return
    let isCurrent = true
    Promise.all([api.getRun(selectedRunId), api.getTimeline(selectedRunId)])
      .then(([ov, tl]) => {
        if (isCurrent) {
          setOverview(ov)
          setTimeline(tl)
          setLoadedRunId(selectedRunId)
        }
      })
      .catch(() => {
        if (isCurrent) {
          setError("Failed to load run data")
          setLoadedRunId(selectedRunId)
        }
      })
    return () => { isCurrent = false }
  }, [selectedRunId])

  useEffect(() => {
    if (workspaceMode !== "dashboard") return
    let isCurrent = true
    api.getDashboard("24h")
      .then((data) => { if (isCurrent) setDashboard(data) })
      .catch(() => setError("Failed to load dashboard"))
    return () => { isCurrent = false }
  }, [workspaceMode])

  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
  }, [selectedRunId])

  useEventStream(selectedRunId, useCallback((evt) => {
    if (!selectedRunId || evt.type === "connected" || evt.type === "heartbeat") return
    // A run records events in bursts: reload once they settle instead of once per event.
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
    refreshTimer.current = setTimeout(() => {
      api.getTimeline(selectedRunId).then(setTimeline).catch(() => undefined)
      api.getRun(selectedRunId).then(setOverview).catch(() => undefined)
    }, 250)
    // The sidebar shows the run status: update it as soon as the run ends.
    if (evt.type === "run.completed" || evt.type === "run.failed") refreshRuns()
  }, [selectedRunId, refreshRuns]))

  const selectedRun = useMemo(() => runs.find((r) => r.id === selectedRunId) ?? null, [runs, selectedRunId])
  // The inspector resolves what a decision or graph node refers to from the events of the open run.
  const runEvents = useMemo(() => timeline?.groups.flatMap((group) => group.events) ?? [], [timeline])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is typing in an input/textarea
      const target = e.target as HTMLElement
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return

      switch (e.key) {
        case "j": {
          e.preventDefault()
          setSelectedRunId((current) => {
            if (!current) return runs[0]?.id ?? null
            const idx = runs.findIndex((r) => r.id === current)
            if (idx >= 0 && idx < runs.length - 1) return runs[idx + 1].id
            return current
          })
          break
        }
        case "k": {
          e.preventDefault()
          setSelectedRunId((current) => {
            if (!current) return runs[0]?.id ?? null
            const idx = runs.findIndex((r) => r.id === current)
            if (idx > 0) return runs[idx - 1].id
            return current
          })
          break
        }
        case "r": {
          e.preventDefault()
          refreshRuns()
          break
        }
        case "1": {
          e.preventDefault()
          setBottomTab("audit")
          break
        }
        case "2": {
          e.preventDefault()
          setBottomTab("output")
          break
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [runs, refreshRuns])

  const handleSelectEvent = useCallback((event: EventItem | null) => {
    setSelection((prev) => ({
      runId: selectedRunId,
      event,
      node: event || prev.runId !== selectedRunId ? null : prev.node,
    }))
    if (event) setShowInspector(true)
  }, [selectedRunId])

  const handleSelectGraphNode = useCallback((node: GraphNode | null) => {
    setSelection((prev) => ({
      runId: selectedRunId,
      event: node || prev.runId !== selectedRunId ? null : prev.event,
      node,
    }))
    if (node) setShowInspector(true)
  }, [selectedRunId])

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-bg text-text">
      <Header
        workspaceMode={workspaceMode}
        onWorkspaceChange={setWorkspaceMode}
        selectedRun={selectedRun}
        showSidebar={showSidebar}
        onToggleSidebar={() => setShowSidebar((v) => !v)}
        showBottomPanel={showBottomPanel}
        onToggleBottomPanel={() => setShowBottomPanel((v) => !v)}
        showInspector={showInspector}
        onToggleInspector={() => setShowInspector((v) => !v)}
      />
      <div className="flex flex-1 min-h-0">
        {showSidebar && (
          <Sidebar
            runs={runs}
            selectedRunId={selectedRunId}
            onSelectRun={setSelectedRunId}
            onWorkspaceChange={setWorkspaceMode}
          />
        )}
        <main className="flex-1 min-w-0 flex flex-col">
          {workspaceMode === "dashboard" ? (
            <DashboardView data={dashboard} />
          ) : workspaceMode === "compare" ? (
            <CompareView runs={runs} />
          ) : !overview ? (
            <div className="flex-1 flex items-center justify-center text-muted">
              <p>Select a run or launch a new agent.</p>
            </div>
          ) : (
            <>
              <RunViewToolbar mode={runViewMode} onChange={setRunViewMode} />
              {runViewMode === "timeline" ? (
                <Timeline
                  timeline={timeline}
                  selectedEvent={selectedEvent}
                  onSelectEvent={handleSelectEvent}
                  isLoading={isLoading}
                />
              ) : runViewMode === "graph" ? (
                <ExecutionGraph
                  runId={selectedRunId}
                  view="execution"
                  onSelectNode={handleSelectGraphNode}
                />
              ) : (
                <ExecutionGraph
                  runId={selectedRunId}
                  view="decisions"
                  onSelectNode={handleSelectGraphNode}
                />
              )}
            </>
          )}
          {workspaceMode !== "compare" && showBottomPanel && (
            <BottomPanel
              selectedRunId={selectedRunId}
              overview={overview}
              activeTab={bottomTab}
              onTabChange={setBottomTab}
            />
          )}
        </main>
        {workspaceMode !== "compare" && showInspector && (
          <Inspector
            overview={overview}
            selectedEvent={selectedEvent}
            selectedGraphNode={selectedGraphNode}
            events={runEvents}
            onSelectEvent={handleSelectEvent}
          />
        )}
      </div>
    </div>
  )
}

function RunViewToolbar({ mode, onChange }: { mode: RunView; onChange: (m: RunView) => void }) {
  return (
    <div className="flex items-center gap-1 px-4 py-1.5 border-b border-line bg-bg shrink-0">
      <button
        onClick={() => onChange("timeline")}
        className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded transition-colors ${
          mode === "timeline" ? "bg-accent/10 text-accent" : "text-muted hover:text-text hover:bg-surface-strong"
        }`}
      >
        <List className="w-3 h-3" />
        Timeline
      </button>
      <button
        onClick={() => onChange("graph")}
        className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded transition-colors ${
          mode === "graph" ? "bg-accent/10 text-accent" : "text-muted hover:text-text hover:bg-surface-strong"
        }`}
      >
        <GitBranch className="w-3 h-3" />
        Graph
      </button>
      <button
        onClick={() => onChange("decisions")}
        className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded transition-colors ${
          mode === "decisions" ? "bg-accent/10 text-accent" : "text-muted hover:text-text hover:bg-surface-strong"
        }`}
      >
        <Network className="w-3 h-3" />
        Decisions
      </button>
    </div>
  )
}
