import { Activity, BarChart3, Terminal, GitCompare, Sun, Moon, PanelLeft, PanelBottom, PanelRight } from "lucide-react"
import { useTheme } from "next-themes"
import type { RunListItem } from "../../types"

interface HeaderProps {
  workspaceMode: "run" | "dashboard" | "compare"
  onWorkspaceChange: (mode: "run" | "dashboard" | "compare") => void
  selectedRun: RunListItem | null
  showSidebar: boolean
  onToggleSidebar: () => void
  showBottomPanel: boolean
  onToggleBottomPanel: () => void
  showInspector: boolean
  onToggleInspector: () => void
}

export function Header({
  workspaceMode,
  onWorkspaceChange,
  selectedRun,
  showSidebar,
  onToggleSidebar,
  showBottomPanel,
  onToggleBottomPanel,
  showInspector,
  onToggleInspector,
}: HeaderProps) {
  const { theme, setTheme } = useTheme()

  return (
    <header className="h-10 shrink-0 border-b border-line bg-surface flex items-center justify-between px-4">
      <div className="flex items-center gap-3 min-w-0">
        <Activity className="w-4 h-4 text-accent shrink-0" />
        <h1 className="text-sm font-semibold tracking-tight">TraceAgent</h1>
        <span className="text-xs text-muted hidden sm:inline">Trace & Observe</span>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5 bg-surface-strong rounded-md p-0.5">
          <button
            onClick={() => onWorkspaceChange("dashboard")}
            className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded transition-colors ${
              workspaceMode === "dashboard"
                ? "bg-accent text-white"
                : "text-muted hover:text-text"
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            Dashboard
          </button>
          <button
            onClick={() => onWorkspaceChange("run")}
            className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded transition-colors ${
              workspaceMode === "run"
                ? "bg-accent text-white"
                : "text-muted hover:text-text"
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            Run View
          </button>
          <button
            onClick={() => onWorkspaceChange("compare")}
            className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded transition-colors ${
              workspaceMode === "compare"
                ? "bg-accent text-white"
                : "text-muted hover:text-text"
            }`}
          >
            <GitCompare className="w-3.5 h-3.5" />
            Compare
          </button>
        </div>

        {selectedRun && workspaceMode !== "compare" && (
          <span className="text-xs text-muted hidden lg:inline">
            {selectedRun.id.slice(0, 8)} · {selectedRun.status}
          </span>
        )}

        <div className="flex items-center gap-1">
          <button
            onClick={onToggleSidebar}
            title="Toggle Explorer"
            className={`p-1.5 rounded-md hover:bg-surface-strong transition-colors ${
              showSidebar ? "text-accent" : "text-muted hover:text-text"
            }`}
            aria-label="Toggle Explorer"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
          <button
            onClick={onToggleBottomPanel}
            title="Toggle Bottom Panel"
            className={`p-1.5 rounded-md hover:bg-surface-strong transition-colors ${
              showBottomPanel ? "text-accent" : "text-muted hover:text-text"
            }`}
            aria-label="Toggle Bottom Panel"
          >
            <PanelBottom className="w-4 h-4" />
          </button>
          <button
            onClick={onToggleInspector}
            title="Toggle Inspector"
            className={`p-1.5 rounded-md hover:bg-surface-strong transition-colors ${
              showInspector ? "text-accent" : "text-muted hover:text-text"
            }`}
            aria-label="Toggle Inspector"
          >
            <PanelRight className="w-4 h-4" />
          </button>
        </div>

        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="p-1.5 rounded-md hover:bg-surface-strong text-muted hover:text-text transition-colors"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>
      </div>
    </header>
  )
}
