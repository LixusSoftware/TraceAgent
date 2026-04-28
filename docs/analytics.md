# Analitica y Explicabilidad

Este documento resume lo que expone el visor en el detalle de un run y como se calcula.

## Metadatos de ejecucion

`GET /api/runs/{id}` devuelve el resumen principal del run:

- `status`, `started_at`, `ended_at`
- `tool_count`, `error_count`, `retry_count`, `artifact_count`
- `provider`, `model`
- `metadata`: metadata original del run
- `execution`: bloque derivado con estado y contadores
- `tool_chain`: secuencia consolidada de llamadas a tools

`execution` incluye:

- `duration_ms`
- `total_event_count`
- `model_turn_count`
- `assistant_turn_count`
- `tool_request_count`
- `tool_success_count`
- `tool_failure_count`
- `command_count`
- `command_failure_count`
- `file_read_count`
- `file_write_count`
- `patch_count`
- `registered_tool_count`
- `current_state`
- `last_event_type`, `last_event_actor`, `last_event_at`
- `token_usage`

## Tool chain

`tool_chain` agrupa los eventos `tool.requested`, `tool.started`, `tool.succeeded`, `tool.failed` y `artifact.created` por `step_id` o `call_id`.

Cada item expone:

- `call_id`
- `step_id`
- `parent_step_id`
- `tool_name`
- `status`
- `event_ids`
- `requested_at`, `started_at`, `completed_at`
- `duration_ms`
- `provider`, `model`
- `args_summary`
- `output_summary`
- `stdout_summary`, `stderr_summary`
- `error_summary`, `error_code`
- `artifact_count`

Esto alimenta dos vistas:

- la lista lateral `Tool chain`
- la lista lateral `Commands`
- la lista lateral `Files`
- el `Tool graph` resumido
- la comparativa lado a lado cuando se selecciona un run parecido

## Side effects de coding agents

El SDK soporta:

- `run.record_command(...)`
- `run.record_file_read(...)`
- `run.record_file_write(...)`
- `run.record_patch(...)`
- `run.record_artifact(...)`

Y wrappers automaticos para los casos comunes:

- `run.commands.run(...)`
- `run.files.read_text(...)`
- `run.files.write_text(...)`
- `run.files.delete(...)`
- `run.files.patch_text(...)`
- `run.artifacts.capture(...)`

Eventos nuevos:

- `command.started`
- `command.succeeded`
- `command.failed`
- `file.read`
- `file.written`
- `patch.applied`
- `artifact.updated`
- `guardrail.input_checked`
- `guardrail.output_checked`
- `guardrail.blocked`

Los eventos de archivo y patch persisten:

- `path`
- `change_type`
- `before_hash`
- `after_hash`
- `diff_summary`
- `line_additions`
- `line_deletions`

Los comandos tambien guardan:

- `command`
- `cwd`
- `exit_code`
- `output_summary`
- `stdout_summary`
- `stderr_summary`

Guardrails guardan en metadata:

- `findings`: lista de hallazgos (prompt injection, PII, secretos)
- `reason`: motivo de bloqueo cuando aplica

## Observabilidad operativa

Si `TRACE_AGENT_AUDIT_METRICS_ENABLED=true`, el backend expone `GET /metrics` con:

- `trace_agent_http_requests_total`
- `trace_agent_http_request_duration_seconds`
- `trace_agent_guardrail_findings_total`
- `trace_agent_guardrail_blocked_total`

Si `TRACE_AGENT_AUDIT_ENABLE_OTEL=true`, FastAPI se instrumenta con OpenTelemetry y exporta spans OTLP.

## Tool graph

`GET /api/runs/{id}/analytics` devuelve un `tool_graph` con nodos por llamada a tool y edges entre pasos padre/hijo.

Objetivo:

- ver la cadena de tools sin el ruido de todos los eventos del timeline
- abrir evidencia directamente desde cada nodo

## Coste y latencia

`tool_metrics` agrega la tool chain por nombre de tool.

Cada fila incluye:

- numero de llamadas
- exitos y fallos
- latencia total, media y maxima
- numero de artefactos
- tokens atribuidos
- coste estimado si existe `TRACE_AGENT_MODEL_PRICING`

La atribucion de tokens es aproximada:

- si una respuesta del modelo genera varias tool calls, los tokens de ese turno se reparten entre esas llamadas
- el objetivo es comparar peso relativo por tool, no hacer facturacion exacta

## Similar runs

`similar_runs` compara el run actual con runs recientes.

La heuristica usa solo senales observables:

- solape de tokens del goal
- tools compartidas
- bonus si comparten `agent_name`
- bonus si comparten `metadata.scenario`

No se usan cadenas internas de razonamiento.

Cada resultado devuelve:

- `run_id`
- `agent_name`
- `goal`
- `status`
- `duration_ms`
- `tool_count`, `error_count`, `retry_count`
- `provider`, `model`
- `similarity_score`
- `shared_tools`
- `reason`

La UI permite dos acciones:

- `Abrir`: cambia el foco al otro run
- `Comparar`: abre una vista lado a lado sin perder el run actual

La comparativa reutiliza `GET /api/runs/{id}` y `GET /api/runs/{id}/explanation` para mostrar:

- metricas base de ambos runs
- delta de tools, errores, retries y tokens
- tools compartidas y exclusivas
- turning points de ambos lados

## Compare workspace

El debugger lado a lado usa `GET /api/runs/compare`.

La respuesta devuelve:

- `left_run`, `right_run`
- `overview_diff`
- `divergence`
- `aligned_timeline`
- `tool_diff`
- `command_diff`
- `file_diff`
- `artifact_diff`
- `decision_diff`
- `root_cause`
- `evidence`

`root_cause` clasifica v1 con:

- `bad_tool_selection`
- `retry_without_adaptation`
- `provider_failure`
- `command_failure`
- `missing_context`
- `dead_end_branch`
- `artifact_mismatch`
- `file_change_divergence`
- `no_observable_root_cause`

## Filtros

`GET /api/runs/{id}/analytics` soporta:

- `same_agent_only=true|false`
- `status=completed|failed|running`
- `shared_tools_only=true|false`
- `min_score=0.0..1.0`
- `limit=1..20`

Ejemplos:

```text
/api/runs/<run_id>/analytics?same_agent_only=true
/api/runs/<run_id>/analytics?status=failed&shared_tools_only=true
/api/runs/<run_id>/analytics?min_score=0.45&limit=3
```

## Narrativa y turning points

La explicacion sale de `GET /api/runs/{id}/explanation`.

Incluye:

- `narrative`: frases cortas con `evidence_event_ids`
- `decisions`: turning points derivados
- `flags`: senales como loops o blockers
- `evidence`: mapa de eventos redactados

Reglas del MVP:

- no se guarda chain-of-thought
- no se inventan alternativas si no aparecen en eventos reales
- cada frase debe poder enlazar a evidencia observable
