import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import type { Artifact, EventItem, ExplanationResponse, RunOverview } from "../types";
import { formatMetadataValue, formatMs, formatWhen, prettifyState } from "../view-utils";

type InspectorPanelProps = {
  workspaceMode: "run" | "compare" | "dashboard";
  overview: RunOverview | null;
  explanation: ExplanationResponse | null;
  artifacts: Artifact[];
  selectedEvents: EventItem[];
  selectedPrimaryEvent: EventItem | null;
  compareLeftEvents: EventItem[];
  compareRightEvents: EventItem[];
  comparePrimaryLeftEvent: EventItem | null;
  comparePrimaryRightEvent: EventItem | null;
  onSelectEvidence: (eventIds: number[], eventId?: number | null) => void;
};

type RunInspectorView = "evidence" | "execution" | "causality" | "activity" | "artifacts";

const INSPECTOR_VIEW_ITEMS: Array<{ id: RunInspectorView; label: string }> = [
  { id: "evidence", label: "Evidence" },
  { id: "execution", label: "Execution" },
  { id: "causality", label: "Causality" },
  { id: "activity", label: "Activity" },
  { id: "artifacts", label: "Artifacts" }
];

function InspectorViewSwitcher({
  view,
  onViewChange
}: {
  view: RunInspectorView;
  onViewChange: (view: RunInspectorView) => void;
}) {
  const handleSwitcherKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = INSPECTOR_VIEW_ITEMS.findIndex((item) => item.id === view);
    if (currentIndex < 0) {
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      const nextItem = INSPECTOR_VIEW_ITEMS[(currentIndex + 1) % INSPECTOR_VIEW_ITEMS.length];
      onViewChange(nextItem.id);
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      const previousIndex = (currentIndex - 1 + INSPECTOR_VIEW_ITEMS.length) % INSPECTOR_VIEW_ITEMS.length;
      onViewChange(INSPECTOR_VIEW_ITEMS[previousIndex].id);
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      onViewChange(INSPECTOR_VIEW_ITEMS[0].id);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      onViewChange(INSPECTOR_VIEW_ITEMS[INSPECTOR_VIEW_ITEMS.length - 1].id);
    }
  };

  return (
    <section className="panel-surface inspector-view-switch">
      <div className="section-head">
        <span>Inspector views</span>
        <small>Task focused</small>
      </div>
      <select
        className="inspector-view-select"
        aria-label="Inspector sections"
        value={view}
        onChange={(event) => onViewChange(event.target.value as RunInspectorView)}
      >
        {INSPECTOR_VIEW_ITEMS.map((item) => (
          <option key={`mobile-${item.id}`} value={item.id}>
            {item.label}
          </option>
        ))}
      </select>
      <div className="inspector-view-buttons" role="group" aria-label="Inspector sections" onKeyDown={handleSwitcherKeyDown}>
        {INSPECTOR_VIEW_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`inspector-view-button ${view === item.id ? "active" : ""}`}
            aria-pressed={view === item.id}
            onClick={() => onViewChange(item.id as RunInspectorView)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function CompareInspector({
  compareLeftEvents,
  compareRightEvents,
  comparePrimaryLeftEvent,
  comparePrimaryRightEvent
}: Pick<
  InspectorPanelProps,
  "compareLeftEvents" | "compareRightEvents" | "comparePrimaryLeftEvent" | "comparePrimaryRightEvent"
>) {
  return (
    <>
      <section className="panel-surface">
        <div className="section-head">
          <span>Left evidence</span>
          <small>{compareLeftEvents.length}</small>
        </div>
        <div className="evidence-stack">
          {compareLeftEvents.length === 0 && <p className="empty-copy">Select a compare item to inspect left-side evidence.</p>}
          {compareLeftEvents.map((event) => (
            <article key={`left-${event.id}`} className="evidence-item">
              <div className="evidence-meta">
                <strong>{event.type}</strong>
                <small>{formatWhen(event.timestamp)}</small>
              </div>
              <p>{event.summary}</p>
              <span>{event.tool_name ?? event.actor}</span>
            </article>
          ))}
        </div>
        {comparePrimaryLeftEvent && (
          <div className="metadata-block metadata-block-tight">
            <div className="metadata-head">
              <span>Left metadata</span>
              <small>{Object.keys(comparePrimaryLeftEvent.metadata).length}</small>
            </div>
            {Object.keys(comparePrimaryLeftEvent.metadata).length === 0 && <p className="empty-copy">No extra metadata for this left event.</p>}
            {Object.entries(comparePrimaryLeftEvent.metadata).map(([key, value]) => (
              <div key={`left-${key}`} className="metadata-row">
                <span>{key}</span>
                <strong>{formatMetadataValue(value)}</strong>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel-surface">
        <div className="section-head">
          <span>Right evidence</span>
          <small>{compareRightEvents.length}</small>
        </div>
        <div className="evidence-stack">
          {compareRightEvents.length === 0 && <p className="empty-copy">Select a compare item to inspect right-side evidence.</p>}
          {compareRightEvents.map((event) => (
            <article key={`right-${event.id}`} className="evidence-item">
              <div className="evidence-meta">
                <strong>{event.type}</strong>
                <small>{formatWhen(event.timestamp)}</small>
              </div>
              <p>{event.summary}</p>
              <span>{event.tool_name ?? event.actor}</span>
            </article>
          ))}
        </div>
        {comparePrimaryRightEvent && (
          <div className="metadata-block metadata-block-tight">
            <div className="metadata-head">
              <span>Right metadata</span>
              <small>{Object.keys(comparePrimaryRightEvent.metadata).length}</small>
            </div>
            {Object.keys(comparePrimaryRightEvent.metadata).length === 0 && <p className="empty-copy">No extra metadata for this right event.</p>}
            {Object.entries(comparePrimaryRightEvent.metadata).map(([key, value]) => (
              <div key={`right-${key}`} className="metadata-row">
                <span>{key}</span>
                <strong>{formatMetadataValue(value)}</strong>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function ExecutionSummarySection({ overview }: { overview: RunOverview | null }) {
  if (!overview) {
    return (
      <section className="panel-surface">
        <div className="section-head">
          <span>Execution</span>
          <small>idle</small>
        </div>
        <p className="empty-copy">No execution selected yet.</p>
      </section>
    );
  }

  return (
    <section className="panel-surface">
      <div className="section-head">
        <span>Execution</span>
        <small>{prettifyState(overview.execution.current_state)}</small>
      </div>
      <div className="metric-grid">
        <div>
          <span>Duration</span>
          <strong>{formatMs(overview.execution.duration_ms)}</strong>
        </div>
        <div>
          <span>Model turns</span>
          <strong>{overview.execution.model_turn_count}</strong>
        </div>
        <div>
          <span>Tool requests</span>
          <strong>{overview.execution.tool_request_count}</strong>
        </div>
        <div>
          <span>Commands</span>
          <strong>{overview.execution.command_count}</strong>
        </div>
        <div>
          <span>Registered tools</span>
          <strong>{overview.execution.registered_tool_count}</strong>
        </div>
        <div>
          <span>Last event</span>
          <strong>{overview.execution.last_event_type ?? "-"}</strong>
        </div>
        <div>
          <span>Last seen</span>
          <strong>{formatWhen(overview.execution.last_event_at)}</strong>
        </div>
      </div>
      <div className="token-strip">
        <div>
          <span>Prompt</span>
          <strong>{overview.execution.token_usage.prompt_tokens}</strong>
        </div>
        <div>
          <span>Completion</span>
          <strong>{overview.execution.token_usage.completion_tokens}</strong>
        </div>
        <div>
          <span>Reasoning</span>
          <strong>{overview.execution.token_usage.reasoning_tokens}</strong>
        </div>
      </div>
      <div className="metadata-block">
        <div className="metadata-head">
          <span>Run metadata</span>
          <small>{Object.keys(overview.metadata).length}</small>
        </div>
        {Object.keys(overview.metadata).length === 0 && <p className="empty-copy">No extra run metadata.</p>}
        {Object.entries(overview.metadata).map(([key, value]) => (
          <div key={key} className="metadata-row">
            <span>{key}</span>
            <strong>{formatMetadataValue(value)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function EvidenceSection({
  selectedEvents,
  selectedPrimaryEvent
}: {
  selectedEvents: EventItem[];
  selectedPrimaryEvent: EventItem | null;
}) {
  return (
    <section className="panel-surface">
      <div className="section-head">
        <span>Evidence</span>
        <small>{selectedEvents.length}</small>
      </div>
      <div className="evidence-stack">
        {selectedEvents.length === 0 && <p className="empty-copy">Selecciona un nodo, frase o evento para abrir evidencia.</p>}
        {selectedEvents.map((event) => (
          <article key={event.id} className="evidence-item">
            <div className="evidence-meta">
              <strong>{event.type}</strong>
              <small>{formatWhen(event.timestamp)}</small>
            </div>
            <p>{event.summary}</p>
            <span>
              {event.tool_name ?? event.actor}
              {event.error_code ? ` / ${event.error_code}` : ""}
            </span>
          </article>
        ))}
      </div>
      {selectedPrimaryEvent && (
        <div className="metadata-block metadata-block-tight">
          <div className="metadata-head">
            <span>Event metadata</span>
            <small>{Object.keys(selectedPrimaryEvent.metadata).length}</small>
          </div>
          {Object.keys(selectedPrimaryEvent.metadata).length === 0 && <p className="empty-copy">No extra event metadata.</p>}
          {Object.entries(selectedPrimaryEvent.metadata).map(([key, value]) => (
            <div key={key} className="metadata-row">
              <span>{key}</span>
              <strong>{formatMetadataValue(value)}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function CausalitySection({
  explanation,
  overview,
  onSelectEvidence
}: {
  explanation: ExplanationResponse | null;
  overview: RunOverview | null;
  onSelectEvidence: (eventIds: number[], eventId?: number | null) => void;
}) {
  return (
    <>
      <motion.section
        className="panel-surface"
        initial={{ opacity: 0, x: 18 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div className="section-head">
          <span>Por que ocurrio</span>
          <small>{overview?.status ?? "idle"}</small>
        </div>
        <div className="narrative-stack">
          {explanation?.narrative.map((item, index) => (
            <button
              type="button"
              key={`${item.text}-${index}`}
              className="narrative-item"
              onClick={() => onSelectEvidence(item.evidence_event_ids, item.evidence_event_ids[0] ?? null)}
            >
              {item.text}
            </button>
          ))}
          {!explanation?.narrative.length && <p className="empty-copy">La narrativa aparecera al cerrar el run.</p>}
        </div>
      </motion.section>

      <section className="panel-surface">
        <div className="section-head">
          <span>Turning points</span>
          <small>{explanation?.decisions.length ?? 0}</small>
        </div>
        <div className="decision-list">
          {explanation?.decisions.map((decision) => (
            <button
              type="button"
              key={decision.id}
              className="decision-item"
              onClick={() => onSelectEvidence(decision.evidence_event_ids, decision.evidence_event_ids[0] ?? null)}
            >
              <strong>{decision.label}</strong>
              <p>{decision.rationale_summary}</p>
            </button>
          ))}
          {!explanation?.decisions.length && <p className="empty-copy">Aun no se registraron turning points para este run.</p>}
        </div>
      </section>
    </>
  );
}

function ActivitySection({
  overview,
  onSelectEvidence
}: {
  overview: RunOverview | null;
  onSelectEvidence: (eventIds: number[], eventId?: number | null) => void;
}) {
  if (!overview) {
    return (
      <section className="panel-surface">
        <div className="section-head">
          <span>Activity</span>
          <small>idle</small>
        </div>
        <p className="empty-copy">No activity captured yet.</p>
      </section>
    );
  }

  return (
    <>
      <section className="panel-surface">
        <div className="section-head">
          <span>Tool chain</span>
          <small>{overview.tool_chain.length}</small>
        </div>
        <div className="tool-chain-list">
          {overview.tool_chain.map((item) => (
            <button
              type="button"
              key={`${item.call_id ?? item.step_id}-${item.tool_name}`}
              className="tool-chain-item"
              onClick={() => onSelectEvidence(item.event_ids, item.event_ids[0] ?? null)}
            >
              <div className="tool-chain-head">
                <strong>{item.tool_name}</strong>
                <span className={`tool-status status-${item.status}`}>{prettifyState(item.status)}</span>
              </div>
              <p>{item.error_summary ?? item.output_summary ?? item.args_summary ?? "No summary captured."}</p>
              <small>
                {formatMs(item.duration_ms)} / {item.artifact_count} artifacts / {item.call_id ?? item.step_id}
              </small>
            </button>
          ))}
          {!overview.tool_chain.length && <p className="empty-copy">No tool chain captured yet.</p>}
        </div>
      </section>

      <section className="panel-surface">
        <div className="section-head">
          <span>Commands</span>
          <small>{overview.command_chain.length}</small>
        </div>
        <div className="tool-chain-list">
          {overview.command_chain.map((item) => (
            <button
              type="button"
              key={`${item.command_id ?? item.step_id}-${item.command}`}
              className="tool-chain-item"
              onClick={() => onSelectEvidence(item.event_ids, item.event_ids[0] ?? null)}
            >
              <div className="tool-chain-head">
                <strong>{item.command}</strong>
                <span className={`tool-status status-${item.status}`}>{prettifyState(item.status)}</span>
              </div>
              <p>{item.error_summary ?? item.output_summary ?? item.stdout_summary ?? item.cwd ?? "No command summary captured."}</p>
              <small>
                {formatMs(item.duration_ms)} / {item.exit_code ?? "-"} exit / {item.command_id ?? item.step_id}
              </small>
            </button>
          ))}
          {!overview.command_chain.length && <p className="empty-copy">No commands captured yet.</p>}
        </div>
      </section>

      <section className="panel-surface">
        <div className="section-head">
          <span>Files</span>
          <small>{overview.file_activity.length + overview.patch_activity.length}</small>
        </div>
        <div className="tool-chain-list">
          {overview.file_activity.map((item) => (
            <button
              type="button"
              key={`file-${item.event_id}`}
              className="tool-chain-item"
              onClick={() => onSelectEvidence([item.event_id], item.event_id)}
            >
              <div className="tool-chain-head">
                <strong>{item.path}</strong>
                <span className={`tool-status status-${item.status}`}>{item.event_type}</span>
              </div>
              <p>{item.diff_summary ?? item.summary}</p>
              <small>
                {item.change_type ?? "read"} / +{item.line_additions ?? 0} -{item.line_deletions ?? 0}
              </small>
            </button>
          ))}
          {overview.patch_activity.map((item) => (
            <button
              type="button"
              key={`patch-${item.event_id}`}
              className="tool-chain-item"
              onClick={() => onSelectEvidence([item.event_id], item.event_id)}
            >
              <div className="tool-chain-head">
                <strong>{item.path}</strong>
                <span className={`tool-status status-${item.status}`}>patch</span>
              </div>
              <p>{item.diff_summary ?? item.summary}</p>
              <small>
                +{item.line_additions ?? 0} -{item.line_deletions ?? 0}
              </small>
            </button>
          ))}
          {overview.file_activity.length + overview.patch_activity.length === 0 && <p className="empty-copy">No file activity captured yet.</p>}
        </div>
      </section>
    </>
  );
}

function ArtifactsSection({ artifacts }: { artifacts: Artifact[] }) {
  return (
    <section className="panel-surface">
      <div className="section-head">
        <span>Artifacts</span>
        <small>{artifacts.length}</small>
      </div>
      <div className="artifact-list">
        {artifacts.map((artifact) => (
          <article key={artifact.id} className="artifact-item">
            <strong>{artifact.label}</strong>
            <p>{artifact.summary}</p>
          </article>
        ))}
        {artifacts.length === 0 && <p className="empty-copy">No hay artefactos persistidos en este run.</p>}
      </div>
    </section>
  );
}

function RunInspector({
  overview,
  explanation,
  artifacts,
  selectedEvents,
  selectedPrimaryEvent,
  onSelectEvidence
}: Pick<
  InspectorPanelProps,
  "overview" | "explanation" | "artifacts" | "selectedEvents" | "selectedPrimaryEvent" | "onSelectEvidence"
>) {
  const [view, setView] = useState<RunInspectorView>("evidence");

  useEffect(() => {
    if (selectedEvents.length > 0) {
      setView("evidence");
    }
  }, [selectedEvents.length]);

  return (
    <>
      <InspectorViewSwitcher view={view} onViewChange={setView} />

      {view === "execution" && <ExecutionSummarySection overview={overview} />}
      {view === "evidence" && <EvidenceSection selectedEvents={selectedEvents} selectedPrimaryEvent={selectedPrimaryEvent} />}
      {view === "causality" && <CausalitySection explanation={explanation} overview={overview} onSelectEvidence={onSelectEvidence} />}
      {view === "activity" && <ActivitySection overview={overview} onSelectEvidence={onSelectEvidence} />}
      {view === "artifacts" && <ArtifactsSection artifacts={artifacts} />}
    </>
  );
}

export function InspectorPanel(props: InspectorPanelProps) {
  if (props.workspaceMode === "compare") {
    return (
      <CompareInspector
        compareLeftEvents={props.compareLeftEvents}
        compareRightEvents={props.compareRightEvents}
        comparePrimaryLeftEvent={props.comparePrimaryLeftEvent}
        comparePrimaryRightEvent={props.comparePrimaryRightEvent}
      />
    );
  }

  return (
    <RunInspector
      overview={props.overview}
      explanation={props.explanation}
      artifacts={props.artifacts}
      selectedEvents={props.selectedEvents}
      selectedPrimaryEvent={props.selectedPrimaryEvent}
      onSelectEvidence={props.onSelectEvidence}
    />
  );
}

export default InspectorPanel;

