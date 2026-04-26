import { motion } from "framer-motion";
import type { DiffPair, RunCompareResponse, RunListItem } from "../types";
import { formatDelta } from "../view-utils";

type CompareWorkspaceProps = {
  runs: RunListItem[];
  selectedRunId: string | null;
  comparedRunId: string | null;
  compareData: RunCompareResponse | null;
  error: string | null;
  isLoading: boolean;
  hasComparableRuns: boolean;
  onSelectLeftRun: (runId: string) => void;
  onSelectRightRun: (runId: string) => void;
  onBackToRun: () => void;
  onSelectionChange: (selection: { left: number[]; right: number[] }) => void;
};

function ComparePairList({
  title,
  items,
  onSelectionChange
}: {
  title: string;
  items: DiffPair[];
  onSelectionChange: (selection: { left: number[]; right: number[] }) => void;
}) {
  return (
    <section className="panel-surface compare-panel">
      <div className="section-head">
        <span>{title}</span>
        <small>{items.length}</small>
      </div>
      <div className="compare-pair-list">
        {items.map((item, index) => (
          <button
            type="button"
            key={`${title}-${index}-${item.summary}`}
            className={`compare-pair-item relation-${item.relation}`}
            onClick={() =>
              onSelectionChange({
                left: item.left?.event_ids ?? [],
                right: item.right?.event_ids ?? []
              })
            }
          >
            <div className="compare-pair-head">
              <strong>{item.summary}</strong>
              <span>{item.relation}</span>
            </div>
            <div className="compare-pair-columns">
              <div>
                <small>Left</small>
                <p>{item.left?.label ?? "-"}</p>
                <em>{item.left?.summary ?? item.left?.status ?? "no event"}</em>
              </div>
              <div>
                <small>Right</small>
                <p>{item.right?.label ?? "-"}</p>
                <em>{item.right?.summary ?? item.right?.status ?? "no event"}</em>
              </div>
            </div>
          </button>
        ))}
        {items.length === 0 && <p className="empty-copy">No compare data for this section.</p>}
      </div>
    </section>
  );
}

export function CompareWorkspace({
  runs,
  selectedRunId,
  comparedRunId,
  compareData,
  error,
  isLoading,
  hasComparableRuns,
  onSelectLeftRun,
  onSelectRightRun,
  onBackToRun,
  onSelectionChange
}: CompareWorkspaceProps) {
  if (isLoading && selectedRunId && comparedRunId) {
    return (
      <div className="empty-stage">
        <h2>Preparando comparacion</h2>
        <p>Sincronizando datos de ambos runs para mostrar divergencias y causa raiz.</p>
      </div>
    );
  }

  if (!compareData || !selectedRunId || !comparedRunId) {
    return (
      <div className="empty-stage">
        <h2>Preparando comparacion</h2>
        <p>
          {hasComparableRuns
            ? "Selecciona dos runs y espera a que se cargue el compare workspace."
            : "No hay suficientes runs para comparar. Ejecuta al menos dos runs y vuelve a intentarlo."}
        </p>
        {error && <p className="error-text">{error}</p>}
      </div>
    );
  }

  const leftRun = compareData.left_run;
  const rightRun = compareData.right_run;
  const rightRunOptions = runs.filter((run) => run.id !== selectedRunId);

  return (
    <>
      <motion.header
        className="run-header"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div>
          <p className="eyebrow">Compare workspace</p>
          <h2>Run divergence debugger</h2>
          <div className="compare-picker-row">
            <label className="filter-field compare-picker">
              <span>Left run</span>
              <select value={selectedRunId} disabled={isLoading} onChange={(event) => onSelectLeftRun(event.target.value)}>
                {runs.map((run) => (
                  <option key={`left-${run.id}`} value={run.id}>
                    {run.agent_name} / {run.goal}
                  </option>
                ))}
              </select>
            </label>
            <label className="filter-field compare-picker">
              <span>Right run</span>
              <select
                value={comparedRunId}
                disabled={isLoading || rightRunOptions.length === 0}
                onChange={(event) => onSelectRightRun(event.target.value)}
              >
                {rightRunOptions.map((run) => (
                  <option key={`right-${run.id}`} value={run.id}>
                    {run.agent_name} / {run.goal}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="secondary-action" disabled={isLoading} onClick={onBackToRun}>
              Volver al run
            </button>
          </div>
          <p className="meta-line">
            {leftRun.agent_name} vs {rightRun.agent_name} / {leftRun.provider ?? "provider"} / {rightRun.provider ?? "provider"}
          </p>
        </div>
        <div className="header-metrics">
          <div>
            <span>Delta tools</span>
            <strong>{formatDelta(0, compareData.overview_diff.tool_count_delta)}</strong>
          </div>
          <div>
            <span>Delta cmds</span>
            <strong>{formatDelta(0, compareData.overview_diff.command_count_delta)}</strong>
          </div>
          <div>
            <span>Delta errors</span>
            <strong>{formatDelta(0, compareData.overview_diff.error_count_delta)}</strong>
          </div>
          <div>
            <span>Delta retries</span>
            <strong>{formatDelta(0, compareData.overview_diff.retry_count_delta)}</strong>
          </div>
          <div>
            <span>Delta tokens</span>
            <strong>{formatDelta(0, compareData.overview_diff.token_total_delta)}</strong>
          </div>
        </div>
      </motion.header>

      <section className="workspace-section">
        <div className="workspace-section-head">
          <div>
            <p className="eyebrow">Comparison</p>
            <h3>First mismatch, aligned steps and causal evidence</h3>
          </div>
          <p className="section-note">Selecciona cualquier diff para sincronizar evidencia izquierda y derecha en el inspector.</p>
        </div>

        <section className="panel-surface divergence-strip">
          <div className="section-head">
            <span>First divergence</span>
            <small>{compareData.divergence?.first_mismatch_kind ?? "aligned"}</small>
          </div>
          <button
            type="button"
            className="divergence-summary"
            data-testid="compare-divergence"
            onClick={() =>
              onSelectionChange({
                left: compareData.divergence?.left_event_ids ?? [],
                right: compareData.divergence?.right_event_ids ?? []
              })
            }
          >
            {compareData.divergence?.summary ?? "No observable divergence between the selected runs."}
          </button>
        </section>

        <div className="compare-workspace-grid">
          <section className="panel-surface compare-timeline-panel">
            <div className="section-head">
              <span>Aligned timeline</span>
              <small>{compareData.aligned_timeline.length}</small>
            </div>
            <div className="compare-pair-list">
              {compareData.aligned_timeline.map((item, index) => (
                <button
                  type="button"
                  key={`timeline-${index}-${item.summary}`}
                  className={`compare-pair-item relation-${item.relation}`}
                  onClick={() =>
                    onSelectionChange({
                      left: item.left?.event_ids ?? [],
                      right: item.right?.event_ids ?? []
                    })
                  }
                >
                  <div className="compare-pair-head">
                    <strong>{item.kind}</strong>
                    <span>{item.relation}</span>
                  </div>
                  <p>{item.summary}</p>
                  <div className="compare-pair-columns">
                    <div>
                      <small>Left</small>
                      <p>{item.left?.label ?? "-"}</p>
                      <em>{item.left?.status ?? "no event"}</em>
                    </div>
                    <div>
                      <small>Right</small>
                      <p>{item.right?.label ?? "-"}</p>
                      <em>{item.right?.status ?? "no event"}</em>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="panel-surface root-cause-panel">
            <div className="section-head">
              <span>Root cause</span>
              <small>{compareData.root_cause.confidence}</small>
            </div>
            <button
              type="button"
              className="root-cause-card"
              data-testid="compare-root-cause"
              onClick={() =>
                onSelectionChange({
                  left: compareData.root_cause.supporting_event_ids.left ?? [],
                  right: compareData.root_cause.supporting_event_ids.right ?? []
                })
              }
            >
              <strong>{compareData.root_cause.label}</strong>
              <p>{compareData.root_cause.summary}</p>
              <small>{compareData.root_cause.impact_summary}</small>
            </button>

            <div className="compare-overview-grid">
              <div>
                <span>Left</span>
                <strong>{leftRun.status}</strong>
                <small>{leftRun.goal}</small>
              </div>
              <div>
                <span>Right</span>
                <strong>{rightRun.status}</strong>
                <small>{rightRun.goal}</small>
              </div>
            </div>
          </section>
        </div>

        <div className="compare-diff-grid">
          <ComparePairList title="Tool diff" items={compareData.tool_diff} onSelectionChange={onSelectionChange} />
          <ComparePairList title="Command diff" items={compareData.command_diff} onSelectionChange={onSelectionChange} />
          <ComparePairList title="File diff" items={compareData.file_diff} onSelectionChange={onSelectionChange} />
          <ComparePairList title="Artifact diff" items={compareData.artifact_diff} onSelectionChange={onSelectionChange} />
        </div>
      </section>
    </>
  );
}
