import { useMemo, useState } from "react"
import { Search, RefreshCw, Circle, FilterX } from "lucide-react"
import type { RunListItem } from "../../types"

interface SidebarProps {
  runs: RunListItem[]
  selectedRunId: string | null
  onSelectRun: (id: string) => void
  onWorkspaceChange: (mode: "run" | "dashboard") => void
}

export function Sidebar({ runs, selectedRunId, onSelectRun }: SidebarProps) {
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("")

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return runs.filter((r) => {
      if (statusFilter && r.status !== statusFilter) return false
      if (!q) return true
      const text = [r.agent_name, r.goal, r.status, r.provider, r.model, r.id].join(" ").toLowerCase()
      return text.includes(q)
    })
  }, [runs, search, statusFilter])

  const stats = useMemo(() => {
    if (runs.length === 0) return null
    const completed = runs.filter((r) => r.status === "completed").length
    const failed = runs.filter((r) => r.status === "failed").length
    const pct = runs.length > 0 ? Math.round((completed / runs.length) * 100) : 0
    return { total: runs.length, completed, failed, errors: runs.reduce((s, r) => s + r.error_count, 0), pct }
  }, [runs])

  return (
    <aside className="w-72 min-w-72 border-r border-line bg-surface flex flex-col shrink-0">
      <div className="px-3 py-2 border-b border-line">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">Explorer</span>
          <span className="text-[10px] text-muted">{filtered.length} runs</span>
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search runs..."
            className="w-full pl-7 pr-2 py-1.5 text-xs bg-bg border border-line rounded-md focus:outline-none focus:border-accent placeholder:text-muted"
          />
        </div>
        <div className="flex gap-2 mt-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="flex-1 text-[11px] bg-bg border border-line rounded px-2 py-1 focus:outline-none focus:border-accent"
          >
            <option value="">All</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
          {(search || statusFilter) && (
            <button
              onClick={() => { setSearch(""); setStatusFilter("") }}
              className="px-2 py-1 text-[11px] text-muted hover:text-text border border-line rounded hover:bg-surface-strong transition-colors"
            >
              <FilterX className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <p className="px-3 py-4 text-xs text-muted text-center">No runs found.</p>
        )}
        {filtered.map((run) => (
          <button
            key={run.id}
            onClick={() => onSelectRun(run.id)}
            className={`w-full text-left px-3 py-2 flex items-start gap-2.5 transition-colors border-l-2 ${
              run.id === selectedRunId
                ? "bg-surface-strong border-accent"
                : "border-transparent hover:bg-surface-strong"
            }`}
          >
            <StatusDot status={run.status} />
            <div className="min-w-0">
              <p className={`text-xs font-medium truncate ${run.id === selectedRunId ? "text-accent" : "text-text"}`}>
                {run.agent_name}
              </p>
              <p className="text-[11px] text-muted truncate">{run.goal || "No goal"}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-muted">{run.id.slice(0, 8)}</span>
                {run.status === "running" && (
                  <RefreshCw className="w-3 h-3 text-warning animate-spin" />
                )}
              </div>
            </div>
          </button>
        ))}
      </div>

      {stats && (
        <div className="px-3 py-2.5 border-t border-line bg-bg shrink-0">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-2">Session Stats</p>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-muted">Total</span>
              <span className="font-medium">{stats.total}</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-muted">OK</span>
              <span className="font-medium text-accent">{stats.pct}%</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-muted">Failed</span>
              <span className={`font-medium ${stats.failed > 0 ? "text-danger" : ""}`}>{stats.failed}</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-muted">Errors</span>
              <span className={`font-medium ${stats.errors > 0 ? "text-warning" : ""}`}>{stats.errors}</span>
            </div>
          </div>
          <div className="mt-2 h-1 bg-line rounded-full overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all"
              style={{ width: `${stats.pct}%` }}
            />
          </div>
        </div>
      )}
    </aside>
  )
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "completed" ? "bg-accent" :
    status === "failed" ? "bg-danger" :
    status === "running" ? "bg-warning animate-pulse" :
    "bg-muted"
  return <Circle className={`w-2 h-2 shrink-0 mt-1 ${color} rounded-full`} fill="currentColor" />
}
