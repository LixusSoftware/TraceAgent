import type { RunAnalytics, SimilarRunFilters } from "../types";
import { formatMs } from "../view-utils";

type SimilarRunsPanelProps = {
  analytics: RunAnalytics | null;
  comparedRunId: string | null;
  filters: SimilarRunFilters;
  isLoading?: boolean;
  onFiltersChange: (filters: SimilarRunFilters) => void;
  onCompare: (runId: string) => void;
  onOpen: (runId: string) => void;
};

export function SimilarRunsPanel({
  analytics,
  comparedRunId,
  filters,
  isLoading = false,
  onFiltersChange,
  onCompare,
  onOpen
}: SimilarRunsPanelProps) {
  return (
    <section className="panel-surface" aria-busy={isLoading}>
      <div className="section-head">
        <span>Similar runs</span>
        <small>{analytics?.similar_runs.length ?? 0}</small>
      </div>
      <div className="similar-filter-stack">
        <div className="similar-filter-row">
          <label className="check-chip">
            <input
              type="checkbox"
              checked={filters.sameAgentOnly}
              disabled={isLoading}
              onChange={(event) =>
                onFiltersChange({
                  ...filters,
                  sameAgentOnly: event.target.checked
                })
              }
            />
            Same agent
          </label>
          <label className="check-chip">
            <input
              type="checkbox"
              checked={filters.sharedToolsOnly}
              disabled={isLoading}
              onChange={(event) =>
                onFiltersChange({
                  ...filters,
                  sharedToolsOnly: event.target.checked
                })
              }
            />
            Shared tools
          </label>
        </div>
        <div className="similar-filter-row similar-filter-row-selects">
          <label className="filter-field">
            <span>Status</span>
            <select
              value={filters.status}
              disabled={isLoading}
              onChange={(event) =>
                onFiltersChange({
                  ...filters,
                  status: event.target.value as SimilarRunFilters["status"]
                })
              }
            >
              <option value="all">all</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="running">running</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Min score</span>
            <select
              value={String(filters.minScore)}
              disabled={isLoading}
              onChange={(event) =>
                onFiltersChange({
                  ...filters,
                  minScore: Number(event.target.value)
                })
              }
            >
              <option value="0.15">15%</option>
              <option value="0.3">30%</option>
              <option value="0.45">45%</option>
              <option value="0.6">60%</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Limit</span>
            <select
              value={String(filters.limit)}
              disabled={isLoading}
              onChange={(event) =>
                onFiltersChange({
                  ...filters,
                  limit: Number(event.target.value)
                })
              }
            >
              <option value="3">3</option>
              <option value="5">5</option>
              <option value="8">8</option>
              <option value="12">12</option>
            </select>
          </label>
        </div>
      </div>
      <div className="similar-run-list" aria-live="polite">
        {analytics?.similar_runs.map((item) => (
          <article
            key={item.run_id}
            className={`similar-run-item ${comparedRunId === item.run_id ? "selected-compare" : ""}`}
          >
            <div className="similar-run-head">
              <strong>{item.agent_name}</strong>
              <span>{Math.round(item.similarity_score * 100)}%</span>
            </div>
            <p>{item.goal}</p>
            <small>
              {formatMs(item.duration_ms)} / {item.tool_count} tools / {item.error_count} errors
            </small>
            <em>{item.reason}</em>
            <div className="similar-run-actions">
              <button type="button" className="secondary-action" disabled={isLoading} onClick={() => onCompare(item.run_id)}>
                Comparar
              </button>
              <button type="button" className="primary-action" disabled={isLoading} onClick={() => onOpen(item.run_id)}>
                Abrir
              </button>
            </div>
          </article>
        ))}
        {isLoading && (
          <p className="empty-copy" role="status">
            Buscando ejecuciones parecidas...
          </p>
        )}
        {!isLoading && !analytics?.similar_runs.length && <p className="empty-copy">No se encontraron runs parecidos todavia.</p>}
      </div>
    </section>
  );
}
