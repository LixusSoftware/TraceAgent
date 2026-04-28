import { useState, useEffect } from "react";
import { Shield, FileOutput } from "lucide-react";
import type { AuditReport, RunOverview, Artifact } from "../../types";
import { api } from "../../api";
import { JsonViewer } from "../JsonViewer";

export type BottomTab = "audit" | "output";

interface BottomPanelProps {
  selectedRunId: string | null;
  overview: RunOverview | null;
  activeTab: BottomTab;
  onTabChange: (tab: BottomTab) => void;
}

export function BottomPanel({ selectedRunId, overview, activeTab, onTabChange }: BottomPanelProps) {
  const [audit, setAudit] = useState<AuditReport | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);

  useEffect(() => {
    if (!selectedRunId) {
      setAudit(null);
      setArtifacts([]);
      return;
    }
    let isCurrent = true;
    setAuditLoading(true);
    api.getAudit(selectedRunId)
      .then((data) => { if (isCurrent) setAudit(data); })
      .catch(() => { if (isCurrent) setAudit(null); })
      .finally(() => { if (isCurrent) setAuditLoading(false); });
    return () => { isCurrent = false; };
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      setArtifacts([]);
      return;
    }
    let isCurrent = true;
    setArtifactsLoading(true);
    api.getArtifacts(selectedRunId)
      .then((data) => { if (isCurrent) setArtifacts(data); })
      .catch(() => { if (isCurrent) setArtifacts([]); })
      .finally(() => { if (isCurrent) setArtifactsLoading(false); });
    return () => { isCurrent = false; };
  }, [selectedRunId]);

  return (
    <div className="shrink-0 border-t border-line bg-surface flex flex-col">
      <div className="flex border-b border-line bg-bg">
        <TabButton tab="audit" active={activeTab} onClick={onTabChange} icon={Shield} label="Audit" />
        <TabButton tab="output" active={activeTab} onClick={onTabChange} icon={FileOutput} label="Output" />
      </div>
      <div className="h-48 p-3 overflow-auto">
        {activeTab === "audit" && (
          <AuditTab audit={audit} loading={auditLoading} />
        )}
        {activeTab === "output" && (
          <OutputTab overview={overview} artifacts={artifacts} loading={artifactsLoading} />
        )}
      </div>
    </div>
  );
}

function AuditTab({ audit, loading }: { audit: AuditReport | null; loading: boolean }) {
  if (loading) {
    return <p className="text-xs text-muted">Loading audit report...</p>;
  }
  if (!audit) {
    return <p className="text-xs text-muted">No audit data available.</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4 text-xs">
        <span className="text-muted">Security Score:</span>
        <span className={`font-semibold ${audit.security_score >= 80 ? "text-accent" : audit.security_score >= 50 ? "text-warning" : "text-danger"}`}>
          {audit.security_score}/100
        </span>
        <span className="text-muted">PII Hits:</span>
        <span className="font-medium">{audit.pii_hit_count}</span>
        <span className="text-muted">Injections:</span>
        <span className="font-medium">{audit.injection_hit_count}</span>
        <span className="text-muted">Secrets:</span>
        <span className="font-medium">{audit.secret_hit_count}</span>
      </div>

      {audit.guardrail_events.length > 0 ? (
        <div className="space-y-2">
          {audit.guardrail_events.map((evt) => (
            <div key={evt.event_id} className="bg-bg border border-line rounded p-2">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${
                  evt.severity === "high" ? "border-danger/30 text-danger bg-danger/10" :
                  evt.severity === "medium" ? "border-warning/30 text-warning bg-warning/10" :
                  "border-info/30 text-info bg-info/10"
                }`}>
                  {evt.severity}
                </span>
                <span className="text-[11px] font-medium">{evt.type}</span>
                <span className="text-[10px] text-muted ml-auto">{evt.scope}</span>
              </div>
              <p className="text-[11px] text-muted mb-1">{evt.summary}</p>
              {evt.findings.length > 0 && (
                <div className="space-y-1">
                  {evt.findings.map((f, i) => (
                    <div key={i} className="text-[10px] text-muted pl-2 border-l border-line">
                      <span className="font-medium text-text">{f.kind}</span>: {f.message}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted">No guardrail events found.</p>
      )}
    </div>
  );
}

function OutputTab({
  overview,
  artifacts,
  loading,
}: {
  overview: RunOverview | null;
  artifacts: Artifact[];
  loading: boolean;
}) {
  if (loading) {
    return <p className="text-xs text-muted">Loading artifacts...</p>;
  }

  const finalOutput = overview?.final_output_summary;
  let parsedJson: unknown = null;
  let isJson = false;
  if (finalOutput) {
    try {
      parsedJson = JSON.parse(finalOutput);
      isJson = true;
    } catch {
      isJson = false;
    }
  }

  return (
    <div className="space-y-3">
      {finalOutput && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-1">Final Output</p>
          {isJson ? (
            <JsonViewer value={parsedJson} maxHeight="140px" />
          ) : (
            <div className="bg-bg border border-line rounded p-2 text-xs text-text whitespace-pre-wrap">
              {finalOutput}
            </div>
          )}
        </div>
      )}

      {artifacts.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted mb-1">Artifacts ({artifacts.length})</p>
          <div className="space-y-2">
            {artifacts.map((art) => (
              <div key={art.id} className="bg-bg border border-line rounded p-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/20">
                    {art.kind}
                  </span>
                  <span className="text-[11px] font-medium">{art.label}</span>
                </div>
                <p className="text-[11px] text-muted mb-1">{art.summary}</p>
                {Object.keys(art.metadata).length > 0 && (
                  <JsonViewer value={art.metadata} maxHeight="120px" />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!finalOutput && artifacts.length === 0 && (
        <p className="text-xs text-muted">No output available.</p>
      )}
    </div>
  );
}

function TabButton({ tab, active, onClick, icon: Icon, label }: {
  tab: BottomTab;
  active: BottomTab;
  onClick: (t: BottomTab) => void;
  icon: typeof Shield;
  label: string;
}) {
  const isActive = active === tab;
  return (
    <button
      onClick={() => onClick(tab)}
      className={`flex items-center gap-1.5 px-4 py-2 text-[11px] font-medium uppercase tracking-wider transition-colors border-t-2 ${
        isActive
          ? "border-accent bg-surface text-text"
          : "border-transparent text-muted hover:text-text hover:bg-surface-strong"
      }`}
    >
      <Icon className="w-3.5 h-3.5" />
      {label}
    </button>
  );
}
