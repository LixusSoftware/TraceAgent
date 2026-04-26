import type { AuditReport, AuditEvent, AuditFinding } from "../types";

type AuditDashboardProps = {
  audit: AuditReport | null;
  isLoading: boolean;
  onSelectEvidence: (eventIds: number[], eventId?: number | null) => void;
};

function scoreColor(score: number): string {
  if (score >= 80) return "#2e7d5a";
  if (score >= 50) return "#c28f27";
  return "#c0392b";
}

function scoreLabel(score: number): string {
  if (score >= 80) return "Secure";
  if (score >= 50) return "Moderate";
  return "At Risk";
}

function SeverityBadge({ severity }: { severity: AuditEvent["severity"] }) {
  const colors: Record<string, { bg: string; color: string }> = {
    high: { bg: "rgba(192,57,43,0.15)", color: "#c0392b" },
    medium: { bg: "rgba(194,143,39,0.15)", color: "#c28f27" },
    low: { bg: "rgba(46,125,90,0.12)", color: "#2e7d5a" },
    info: { bg: "rgba(100,100,100,0.1)", color: "var(--muted)" },
  };
  const c = colors[severity] ?? colors.info;
  return (
    <span
      style={{
        fontSize: "0.65rem",
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.6px",
        padding: "1px 6px",
        borderRadius: "2px",
        background: c.bg,
        color: c.color,
        flexShrink: 0,
      }}
    >
      {severity}
    </span>
  );
}

function ScopeTag({ scope }: { scope: AuditEvent["scope"] }) {
  const labels = { input: "IN", output: "OUT", block: "BLOCK" };
  const colors: Record<string, string> = {
    input: "var(--accent)",
    output: "#c28f27",
    block: "#c0392b",
  };
  return (
    <span
      style={{
        fontSize: "0.65rem",
        fontWeight: 700,
        letterSpacing: "0.8px",
        color: colors[scope] ?? "var(--muted)",
        fontFamily: "monospace",
        flexShrink: 0,
      }}
    >
      {labels[scope] ?? scope.toUpperCase()}
    </span>
  );
}

function SecurityRing({ score }: { score: number }) {
  const radius = 38;
  const cx = 52;
  const cy = 52;
  const stroke = 8;
  const circumference = 2 * Math.PI * radius;
  const filled = (score / 100) * circumference;
  const color = scoreColor(score);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}>
      <svg width={104} height={104} viewBox="0 0 104 104">
        {/* track */}
        <circle cx={cx} cy={cy} r={radius} fill="none" stroke="var(--line)" strokeWidth={stroke} />
        {/* filled arc */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={`${filled} ${circumference}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
        {/* score number */}
        <text x={cx} y={cy + 5} textAnchor="middle" fontSize="18" fontWeight="700" fill={color}>
          {score}
        </text>
      </svg>
      <span
        style={{
          fontSize: "0.7rem",
          fontWeight: 600,
          letterSpacing: "1px",
          textTransform: "uppercase",
          color,
        }}
      >
        {scoreLabel(score)}
      </span>
    </div>
  );
}

function Counter({
  label,
  value,
  icon,
  alertLevel,
}: {
  label: string;
  value: number;
  icon: string;
  alertLevel: "ok" | "warn" | "danger";
}) {
  const clr =
    alertLevel === "danger"
      ? "#c0392b"
      : alertLevel === "warn"
      ? "#c28f27"
      : value > 0
      ? "#c28f27"
      : "var(--muted)";

  return (
    <div
      style={{
        flex: 1,
        minWidth: "80px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "4px",
        padding: "12px 8px",
        borderRadius: "4px",
        background: "var(--bg)",
        border: "1px solid var(--line)",
      }}
    >
      <span style={{ fontSize: "1.2rem" }}>{icon}</span>
      <span style={{ fontSize: "1.4rem", fontWeight: 700, color: clr, lineHeight: 1 }}>
        {value}
      </span>
      <span style={{ fontSize: "0.65rem", color: "var(--muted)", textAlign: "center", textTransform: "uppercase", letterSpacing: "0.5px" }}>
        {label}
      </span>
    </div>
  );
}

function FindingDetail({ finding }: { finding: AuditFinding }) {
  return (
    <div
      style={{
        fontSize: "0.72rem",
        fontFamily: "monospace",
        padding: "4px 8px",
        background: "rgba(0,0,0,0.04)",
        borderRadius: "2px",
        color: "var(--muted)",
        marginTop: "4px",
      }}
    >
      <span style={{ fontWeight: 600, color: "var(--text)" }}>[{finding.kind}]</span>{" "}
      {finding.message}
      {finding.score != null && (
        <span style={{ marginLeft: "6px", opacity: 0.7 }}>score: {finding.score.toFixed(2)}</span>
      )}
      {finding.entity && (
        <span style={{ marginLeft: "6px", opacity: 0.7 }}>entity: {finding.entity}</span>
      )}
    </div>
  );
}

function GuardrailEventRow({
  event,
  onSelect,
}: {
  event: AuditEvent;
  onSelect: (ids: number[]) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect([event.event_id])}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "6px",
        width: "100%",
        textAlign: "left",
        background: "transparent",
        border: "none",
        borderBottom: "1px solid var(--line)",
        padding: "8px 12px",
        cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
        <ScopeTag scope={event.scope} />
        <SeverityBadge severity={event.severity} />
        <span
          style={{
            fontSize: "0.72rem",
            fontFamily: "monospace",
            color: "var(--muted)",
            marginLeft: "auto",
          }}
        >
          seq {event.seq}
        </span>
      </div>
      <p
        style={{
          margin: 0,
          fontSize: "0.8rem",
          color: "var(--text)",
          lineHeight: 1.4,
        }}
      >
        {event.summary}
      </p>
      {event.findings.map((f, i) => (
        <FindingDetail key={i} finding={f} />
      ))}
    </button>
  );
}

export function AuditDashboard({ audit, isLoading, onSelectEvidence }: AuditDashboardProps) {
  if (isLoading) {
    return (
      <div style={{ padding: "24px 16px", color: "var(--muted)", fontFamily: "monospace", fontSize: "0.8rem" }}>
        &gt; Loading audit report...
      </div>
    );
  }

  if (!audit) {
    return (
      <div style={{ padding: "24px 16px", color: "var(--muted)", fontFamily: "monospace", fontSize: "0.8rem" }}>
        &gt; No run selected.
      </div>
    );
  }

  const noEvents = audit.guardrail_event_count === 0;

  return (
    <div
      className="audit-dashboard"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0",
        height: "100%",
        overflowY: "auto",
      }}
    >
      {/* ── Header strip ── */}
      <div
        style={{
          padding: "10px 16px",
          borderBottom: "1px solid var(--line)",
          background: "var(--bg)",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <span
          style={{
            fontSize: "0.7rem",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "1px",
            color: "var(--muted)",
          }}
        >
          Audit Report
        </span>
        <span
          style={{
            fontSize: "0.65rem",
            padding: "1px 6px",
            borderRadius: "2px",
            background: noEvents ? "rgba(46,125,90,0.1)" : "rgba(194,143,39,0.12)",
            color: noEvents ? "#2e7d5a" : "#c28f27",
            fontWeight: 600,
            letterSpacing: "0.5px",
          }}
        >
          {noEvents ? "CLEAN" : `${audit.guardrail_event_count} EVENTS`}
        </span>
      </div>

      {/* ── Scorecard + Counters ── */}
      <div
        style={{
          display: "flex",
          gap: "16px",
          padding: "16px",
          borderBottom: "1px solid var(--line)",
          alignItems: "center",
          flexWrap: "wrap",
          background: "var(--surface)",
        }}
      >
        <SecurityRing score={audit.security_score} />
        <div style={{ display: "flex", gap: "8px", flex: 1, flexWrap: "wrap" }}>
          <Counter
            label="PII detected"
            value={audit.pii_hit_count}
            icon="🔒"
            alertLevel={audit.pii_hit_count > 0 ? "warn" : "ok"}
          />
          <Counter
            label="Injections"
            value={audit.injection_hit_count}
            icon="💉"
            alertLevel={audit.injection_hit_count > 0 ? "danger" : "ok"}
          />
          <Counter
            label="Secrets"
            value={audit.secret_hit_count}
            icon="🗝️"
            alertLevel={audit.secret_hit_count > 0 ? "danger" : "ok"}
          />
          <Counter
            label="Blocks"
            value={audit.block_count}
            icon="🚫"
            alertLevel={audit.block_count > 0 ? "danger" : "ok"}
          />
        </div>
      </div>

      {/* ── Flags ── */}
      {audit.flags.length > 0 && (
        <div
          style={{
            padding: "10px 16px",
            borderBottom: "1px solid var(--line)",
            display: "flex",
            flexWrap: "wrap",
            gap: "6px",
            background: "rgba(192,57,43,0.04)",
          }}
        >
          <span
            style={{
              fontSize: "0.65rem",
              fontWeight: 700,
              textTransform: "uppercase",
              color: "#c0392b",
              letterSpacing: "0.8px",
              alignSelf: "center",
              marginRight: "4px",
            }}
          >
            Flags
          </span>
          {audit.flags.map((flag, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onSelectEvidence(flag.event_ids, flag.event_ids[0] ?? null)}
              style={{
                fontSize: "0.7rem",
                padding: "2px 8px",
                borderRadius: "2px",
                border: "1px solid rgba(192,57,43,0.3)",
                background: "rgba(192,57,43,0.08)",
                color: "#c0392b",
                cursor: "pointer",
                fontWeight: 500,
              }}
            >
              {flag.label}
            </button>
          ))}
        </div>
      )}

      {/* ── Guardrail Event Log ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div
          style={{
            padding: "6px 16px",
            borderBottom: "1px solid var(--line)",
            background: "var(--bg)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span
            style={{
              fontSize: "0.65rem",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "1px",
              color: "var(--muted)",
            }}
          >
            Guardrail Events
          </span>
          <span style={{ fontSize: "0.7rem", color: "var(--muted)" }}>
            {audit.guardrail_events.length} events
          </span>
        </div>

        <div style={{ flex: 1, overflowY: "auto" }}>
          {noEvents ? (
            <div
              style={{
                padding: "20px 16px",
                color: "var(--muted)",
                fontFamily: "monospace",
                fontSize: "0.8rem",
                display: "flex",
                flexDirection: "column",
                gap: "6px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ color: "#2e7d5a", fontSize: "1rem" }}>✓</span>
                No guardrail events for this run.
              </div>
              <div style={{ paddingLeft: "22px", opacity: 0.7, fontSize: "0.72rem" }}>
                Enable guardrails: set{" "}
                <code style={{ background: "var(--bg)", padding: "1px 4px", borderRadius: "2px", whiteSpace: "nowrap" }}>
                  AUDIT_ENABLE_GUARDRAILS=true
                </code>{" "}
                in .env
              </div>
            </div>
          ) : (
            audit.guardrail_events.map((event) => (
              <GuardrailEventRow
                key={event.event_id}
                event={event}
                onSelect={(ids) => onSelectEvidence(ids, ids[0] ?? null)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

