import {
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  Zap,
  Hash,
  TrendingUp,
  AlertTriangle,
  Wrench,
} from "lucide-react";
import type { DashboardResponse } from "../../types";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  CartesianGrid,
} from "recharts";

interface DashboardViewProps {
  data: DashboardResponse | null;
}

const C = {
  accent: "#22c55e",
  accentDim: "rgba(34,197,94,0.2)",
  danger: "#ef4444",
  dangerDim: "rgba(239,68,68,0.2)",
  info: "#3b82f6",
  infoDim: "rgba(59,130,246,0.2)",
  warning: "#f59e0b",
  muted: "#737373",
  grid: "#262626",
  text: "#e5e5e5",
  surface: "#141414",
};

const tooltipStyle = {
  background: C.surface,
  border: `1px solid ${C.grid}`,
  borderRadius: "6px",
  fontSize: 12,
  color: C.text,
};

export function DashboardView({ data }: DashboardViewProps) {
  if (!data) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted text-sm">
        Loading dashboard...
      </div>
    );
  }

  const { stats, trend, top_tools, top_errors, provider_distribution, model_distribution } = data;

  const trendData = trend.map((d) => ({
    date: d.date.slice(5),
    runs: d.runs,
    completed: d.completed,
    failed: d.failed,
  }));

  const providerData = provider_distribution.map((p: Record<string, unknown>) => ({
    name: String(p.provider ?? p.name ?? "unknown"),
    value: Number(p.count ?? p.runs ?? 0),
  }));

  const modelData = model_distribution.map((m: Record<string, unknown>) => ({
    name: String(m.model ?? m.name ?? "unknown"),
    value: Number(m.count ?? m.runs ?? 0),
  }));

  // Token + Tool activity data for bar chart
  const tokenBarData = [
    { name: "Prompt", value: stats.total_prompt_tokens, color: C.info },
    { name: "Completion", value: stats.total_completion_tokens, color: C.accent },
    { name: "Tool Calls", value: stats.total_tools, color: C.warning },
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="flex items-center gap-2 mb-6">
        <TrendingUp className="w-4 h-4 text-accent" />
        <h2 className="text-lg font-semibold">Dashboard</h2>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <KpiCard icon={Activity} label="Total Runs" value={stats.total_runs} />
        <KpiCard icon={CheckCircle} label="Completed" value={stats.completed_runs} color="text-accent" />
        <KpiCard icon={XCircle} label="Failed" value={stats.failed_runs} color="text-danger" />
        <KpiCard icon={Clock} label="Avg Duration" value={stats.avg_duration_ms ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s` : "—"} />
        <KpiCard icon={Zap} label="Errors" value={stats.total_errors} color="text-warning" />
        <KpiCard icon={Hash} label="Tools" value={stats.total_tools} />
        <KpiCard icon={Activity} label="Artifacts" value={stats.total_artifacts} />
        <KpiCard icon={TrendingUp} label="Tokens" value={stats.total_tokens.toLocaleString()} />
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* Trend Area Chart */}
        <div className="bg-surface border border-line rounded-lg p-4">
          <h3 className="text-sm font-medium mb-3">Trend (Last {trend.length} Days)</h3>
          {trendData.length === 0 ? (
            <p className="text-xs text-muted">No trend data.</p>
          ) : (
            <div className="h-48 rounded" style={{ backgroundColor: "#141414" }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData}>
                  <defs>
                    <linearGradient id="colorRuns" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={C.accent} stopOpacity={0.3} />
                      <stop offset="95%" stopColor={C.accent} stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="colorFailed" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={C.danger} stopOpacity={0.3} />
                      <stop offset="95%" stopColor={C.danger} stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                  <XAxis dataKey="date" tick={{ fill: C.muted, fontSize: 10 }} axisLine={{ stroke: C.grid }} />
                  <YAxis tick={{ fill: C.muted, fontSize: 10 }} axisLine={{ stroke: C.grid }} />
                  <Tooltip contentStyle={tooltipStyle} cursor={false} />
                  <Area type="monotone" dataKey="runs" stroke={C.accent} fillOpacity={1} fill="url(#colorRuns)" strokeWidth={2} activeDot={{ r: 3, fill: C.accent, stroke: C.surface }} />
                  <Area type="monotone" dataKey="failed" stroke={C.danger} fillOpacity={1} fill="url(#colorFailed)" strokeWidth={2} activeDot={{ r: 3, fill: C.danger, stroke: C.surface }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Token & Tool Activity */}
        <div className="bg-surface border border-line rounded-lg p-4">
          <h3 className="text-sm font-medium mb-1 flex items-center gap-2">
            <Wrench className="w-3.5 h-3.5 text-warning" />
            Token & Tool Activity
          </h3>
          <p className="text-[10px] text-muted mb-3">Tokens consumed vs tool invocations</p>
          {stats.total_tokens === 0 && stats.total_tools === 0 ? (
            <p className="text-xs text-muted">No activity data.</p>
          ) : (
            <div className="h-48 rounded" style={{ backgroundColor: "#141414" }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={tokenBarData} layout="vertical" margin={{ left: 20, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.grid} horizontal={false} />
                  <XAxis type="number" tick={{ fill: C.muted, fontSize: 10 }} axisLine={{ stroke: C.grid }} />
                  <YAxis dataKey="name" type="category" width={80} tick={{ fill: C.text, fontSize: 10 }} axisLine={{ stroke: C.grid }} />
                  <Tooltip contentStyle={tooltipStyle} cursor={false} formatter={(value) => [typeof value === "number" ? value.toLocaleString() : value, ""]} />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]} activeBar={false}>
                    {tokenBarData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* Top Tools Bar Chart */}
        <div className="bg-surface border border-line rounded-lg p-4">
          <h3 className="text-sm font-medium mb-3">Top Tools</h3>
          {top_tools.length === 0 ? (
            <p className="text-xs text-muted">No tool data.</p>
          ) : (
            <div className="h-48 rounded" style={{ backgroundColor: "#141414" }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={top_tools.slice(0, 8)} layout="vertical" margin={{ left: 0, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.grid} horizontal={false} />
                  <XAxis type="number" tick={{ fill: C.muted, fontSize: 10 }} axisLine={{ stroke: C.grid }} />
                  <YAxis dataKey="tool_name" type="category" width={100} tick={{ fill: C.text, fontSize: 10 }} axisLine={{ stroke: C.grid }} />
                  <Tooltip contentStyle={tooltipStyle} cursor={false} formatter={(value) => [`${value} calls`, "Count"]} />
                  <Bar dataKey="call_count" fill={C.accent} radius={[0, 4, 4, 0]} activeBar={{ fill: C.accent }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Top Errors */}
        <div className="bg-surface border border-line rounded-lg p-4">
          <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-warning" />
            Top Errors
          </h3>
          {top_errors.length === 0 ? (
            <p className="text-xs text-muted">No errors.</p>
          ) : (
            <div className="space-y-2">
              {top_errors.map((err) => (
                <div key={err.error_code} className="flex items-center justify-between text-xs">
                  <span className="font-mono text-danger">{err.error_code}</span>
                  <span className="text-muted">{err.count}×</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Charts Row 3 - Provider & Model */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-surface border border-line rounded-lg p-4">
          <h3 className="text-sm font-medium mb-3">Provider Distribution</h3>
          {providerData.length === 0 ? (
            <p className="text-xs text-muted">No provider data.</p>
          ) : (
            <div className="h-48 rounded" style={{ backgroundColor: "#141414" }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={providerData}
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    paddingAngle={3}
                    dataKey="value"
                    stroke="none"
                  >
                    {providerData.map((_, index) => (
                      <Cell key={`cell-p-${index}`} fill={[C.accent, C.info, C.warning, C.danger][index % 4]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} cursor={false} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="bg-surface border border-line rounded-lg p-4">
          <h3 className="text-sm font-medium mb-3">Model Distribution</h3>
          {modelData.length === 0 ? (
            <p className="text-xs text-muted">No model data.</p>
          ) : (
            <div className="h-48 rounded" style={{ backgroundColor: "#141414" }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={modelData.slice(0, 6)}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                  <XAxis dataKey="name" tick={{ fill: C.muted, fontSize: 9 }} angle={-20} textAnchor="end" height={50} axisLine={{ stroke: C.grid }} />
                  <YAxis tick={{ fill: C.muted, fontSize: 10 }} axisLine={{ stroke: C.grid }} />
                  <Tooltip contentStyle={tooltipStyle} cursor={false} />
                  <Bar dataKey="value" fill={C.info} radius={[4, 4, 0, 0]} activeBar={{ fill: C.info }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  color = "text-text",
}: {
  icon: typeof Activity;
  label: string;
  value: React.ReactNode;
  color?: string;
}) {
  return (
    <div className="bg-surface border border-line rounded-lg p-3">
      <div className="flex items-center gap-2 text-muted mb-1">
        <Icon className="w-4 h-4" />
        <span className="text-[10px] uppercase tracking-wider">{label}</span>
      </div>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
    </div>
  );
}
