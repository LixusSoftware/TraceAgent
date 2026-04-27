import type { DashboardResponse } from "../types";

function KpiCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "4px", padding: "12px 16px", minWidth: "120px" }}>
      <p style={{ margin: "0 0 4px", fontSize: "0.7rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>{label}</p>
      <p style={{ margin: 0, fontSize: "1.4rem", fontWeight: 600, color: color || "var(--text)" }}>{value}</p>
    </div>
  );
}

function BarChart({ data }: { data: { label: string; value: number; color?: string }[] }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {data.map((d) => (
        <div key={d.label} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "0.72rem", color: "var(--muted)", width: "80px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{d.label}</span>
          <div style={{ flex: 1, height: "8px", background: "var(--line)", borderRadius: "4px", overflow: "hidden" }}>
            <div style={{ width: `${(d.value / max) * 100}%`, height: "100%", background: d.color || "var(--accent)", borderRadius: "4px" }} />
          </div>
          <span style={{ fontSize: "0.72rem", color: "var(--text)", width: "30px", textAlign: "right" }}>{d.value}</span>
        </div>
      ))}
    </div>
  );
}

export function DashboardView({ data, isLoading }: { data: DashboardResponse | null; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div style={{ padding: "24px", color: "var(--muted)" }}>
        <p>Loading dashboard...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ padding: "24px", color: "var(--muted)" }}>
        <p>No dashboard data available.</p>
      </div>
    );
  }

  const { stats, trend, top_tools, top_errors, provider_distribution, model_distribution } = data;

  return (
    <div style={{ padding: "24px", overflowY: "auto", height: "100%" }}>
      <h2 style={{ margin: "0 0 16px", fontSize: "1.1rem", fontWeight: 600 }}>Dashboard</h2>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "12px", marginBottom: "24px" }}>
        <KpiCard label="Total Runs" value={stats.total_runs} />
        <KpiCard label="Completed" value={stats.completed_runs} color="#2e7d5a" />
        <KpiCard label="Failed" value={stats.failed_runs} color="#c0392b" />
        <KpiCard label="Running" value={stats.running_runs} color="#c28f27" />
        <KpiCard label="Errors" value={stats.total_errors} color="#c0392b" />
        <KpiCard label="Tools" value={stats.total_tools} />
        <KpiCard label="Artifacts" value={stats.total_artifacts} />
        <KpiCard label="Tokens" value={stats.total_tokens.toLocaleString()} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "16px" }}>
        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "4px", padding: "16px" }}>
          <h3 style={{ margin: "0 0 12px", fontSize: "0.85rem", fontWeight: 600 }}>Trend (last 7 days)</h3>
          <div style={{ display: "flex", alignItems: "flex-end", gap: "4px", height: "120px" }}>
            {trend.map((day) => {
              const maxDay = Math.max(1, ...trend.map((d) => d.runs));
              return (
                <div key={day.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}>
                  <div style={{ display: "flex", flexDirection: "column", width: "100%", gap: "1px", height: "100px", justifyContent: "flex-end" }}>
                    <div style={{ height: `${(day.completed / maxDay) * 100}%`, background: "#2e7d5a", borderRadius: "2px 2px 0 0", minHeight: day.completed > 0 ? "4px" : "0" }} />
                    <div style={{ height: `${(day.failed / maxDay) * 100}%`, background: "#c0392b", borderRadius: "0 0 2px 2px", minHeight: day.failed > 0 ? "4px" : "0" }} />
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--muted)" }}>{day.date.slice(5)}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "4px", padding: "16px" }}>
          <h3 style={{ margin: "0 0 12px", fontSize: "0.85rem", fontWeight: 600 }}>Top Tools</h3>
          <BarChart data={top_tools.map((t) => ({ label: t.tool_name, value: t.call_count }))} />
        </div>

        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "4px", padding: "16px" }}>
          <h3 style={{ margin: "0 0 12px", fontSize: "0.85rem", fontWeight: 600 }}>Top Errors</h3>
          <BarChart data={top_errors.map((e) => ({ label: e.error_code, value: e.count, color: "#c0392b" }))} />
        </div>

        <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "4px", padding: "16px" }}>
          <h3 style={{ margin: "0 0 12px", fontSize: "0.85rem", fontWeight: 600 }}>Providers</h3>
          <BarChart data={provider_distribution.map((p) => ({ label: String(p.provider), value: Number(p.count) }))} />
        </div>
      </div>
    </div>
  );
}
