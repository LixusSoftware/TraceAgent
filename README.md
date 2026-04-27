# Visor Agentico

MVP de observabilidad para agentes con tools.

El proyecto tiene tres piezas:

- `backend`: API FastAPI que crea runs, registra eventos, media turnos de modelo y deriva explicaciones.
- `sdk`: cliente Python para instrumentar agentes y ejecutar tools locales contra el proxy.
- `frontend`: visor React para inspeccionar runs, timeline, grafos, tool chain, evidencia y analitica por run.
- `compare workspace`: modo de debugger para comparar dos runs lado a lado con divergencia, root cause y diffs.

## Arquitectura

- El agente usa `VisorClient` y abre un `RunSession`.
- Cada turno de modelo pasa por el proxy en `POST /api/runs/{id}/turns`.
- Si el modelo pide tools, el SDK las ejecuta localmente y envia el resultado a `POST /api/runs/{id}/tool-results`.
- Al cerrar el run, el backend genera timeline, grafo de ejecucion, grafo de decisiones y narrativa con evidencia.
- El SDK tambien puede registrar side effects de coding agents: comandos, lecturas de archivo, escrituras, patches y artefactos.

Mas detalle en [docs/analytics.md](/C:/Users/evillar/Desktop/test/visor-agentico/docs/analytics.md).

## Arranque rapido

Requisitos: [uv](https://docs.astral.sh/uv/getting-started/installation/) instalado.

Backend:

```bash
uv sync --extra dev
uv run uvicorn visor_agentico.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Con `Makefile` en Windows/PowerShell:

```bash
make backend
make frontend
make dev
```

`make dev` abre backend y frontend en dos ventanas de PowerShell. Tambien tienes:

```bash
make install
make test
make test-ui
make test-e2e
make build
```

Tests:

```bash
uv run pytest
```

Build del frontend:

```bash
cd frontend
npm run build
```

## Variables de entorno

- `VISOR_DATABASE_URL`: por defecto `sqlite:///./visor_agentico.db`; admite PostgreSQL.
- `VISOR_OPENAI_API_KEY`: API key para el adaptador OpenAI.
- `VISOR_OPENAI_BASE_URL`: base URL compatible con OpenAI. Sirve para LM Studio.
- `VISOR_CORS_ORIGINS`: lista separada por comas.
- `VISOR_PROXY_URL`: URL del backend usada por los ejemplos.
- `VISOR_PROXY_TIMEOUT`: timeout del SDK de ejemplo.
- `VISOR_TEST_MODEL`: modelo usado por los ejemplos de LM Studio.
- `VISOR_MODEL_PRICING`: mapa JSON opcional para estimar coste por modelo.
- `VITE_API_BASE_URL`: base URL opcional del frontend cuando no quieres depender del proxy de Vite.
- `VISOR_AUDIT_ENABLE_GUARDRAILS`: activa controles de prompt injection y filtrado de salida.
- `VISOR_AUDIT_FAIL_ON_PROMPT_INJECTION`: bloquea el turno cuando supera el umbral de inyeccion.
- `VISOR_AUDIT_ENABLE_PII_ANONYMIZATION`: anonimiza PII en input/output con Presidio o fallback regex.
- `VISOR_AUDIT_PROMPT_INJECTION_THRESHOLD`: umbral de riesgo para marcar inyeccion (0.0..1.0).
- `VISOR_AUDIT_PII_ENTITIES`: entidades PII permitidas para deteccion.
- `VISOR_AUDIT_METRICS_ENABLED`: habilita endpoint Prometheus `GET /metrics`.
- `VISOR_AUDIT_ENABLE_OTEL`: habilita OpenTelemetry para trazas distribuidas.
- `VISOR_AUDIT_OTEL_SERVICE_NAME`: nombre del servicio para OTel.
- `VISOR_AUDIT_OTEL_EXPORTER_ENDPOINT`: endpoint OTLP opcional.
- `VISOR_AUDIT_OTEL_EXPORTER_PROTOCOL`: `grpc` o `http`.

Ejemplo para `VISOR_MODEL_PRICING`:

```env
VISOR_MODEL_PRICING={"openai:gpt-4.1":{"prompt_per_1k":0.005,"completion_per_1k":0.015}}
```

El repo incluye un [`.env`](/C:/Users/evillar/Desktop/test/visor-agentico/.env) listo para pruebas locales con LM Studio en `http://localhost:4321/v1`.

## Ejemplos

Ejemplo base:

- [examples/sample_agent.py](/C:/Users/evillar/Desktop/test/visor-agentico/examples/sample_agent.py)

Ejemplos para LM Studio:

- [examples/lm_studio_agent.py](/C:/Users/evillar/Desktop/test/visor-agentico/examples/lm_studio_agent.py)
- [examples/lm_studio_planner_agent.py](/C:/Users/evillar/Desktop/test/visor-agentico/examples/lm_studio_planner_agent.py)
- [examples/coding_agent_debugger_demo.py](/C:/Users/evillar/Desktop/test/visor-agentico/examples/coding_agent_debugger_demo.py)

## Wrappers automaticos del SDK

Ademas de `record_command`, `record_file_read`, `record_file_write`, `record_patch` y `record_artifact`, el SDK ahora expone helpers de alto nivel:

- `run.commands.run(...)`
- `run.files.read_text(...)`
- `run.files.write_text(...)`
- `run.files.delete(...)`
- `run.files.patch_text(...)`
- `run.artifacts.capture(...)`

Ejemplo rapido:

```python
from visor_agentico.sdk import VisorClient

client = VisorClient("http://127.0.0.1:8000")
run = client.start_run("coding-agent", "Patch app.py and run tests")

run.files.read_text("src/app.py")
run.files.patch_text("src/app.py", "print('after')\n")
run.commands.run(["python", "-m", "pytest", "-q"], cwd="C:/repo", check=False)
run.artifacts.capture("report", "patch-report", "Patched app.py.")
run.finish({"summary": "Patched app.py."})
```

Estos wrappers ejecutan la accion real y persisten solo resumentes, hashes y metadatos minimos.

### Ejecutar el ejemplo base

En una terminal:

```bash
uvicorn visor_agentico.main:app --reload
```

En otra:

```bash
uv run python examples/sample_agent.py
```

## Probar con LM Studio

Si LM Studio expone una API compatible con OpenAI, puedes usarlo sin token real.

1. Arranca el backend:

```bash
uvicorn visor_agentico.main:app --reload
```

2. Ejecuta un ejemplo:

```bash
uv run python examples/lm_studio_agent.py
uv run python examples/lm_studio_planner_agent.py --scenario meetup_plan
```

## Probar el debugger de coding agents

Este ejemplo no necesita modelo. Solo usa el SDK para registrar side effects reales del agente.

```bash
uv run uvicorn visor_agentico.main:app --reload
uv run python examples/coding_agent_debugger_demo.py --scenario correct_edit
uv run python examples/coding_agent_debugger_demo.py --scenario wrong_file
```

Escenarios disponibles:

- `correct_edit`
- `wrong_file`
- `retry_without_adaptation`
- `same_tools_different_artifact`

## Tests del frontend

Tests unitarios e integracion:

```bash
cd frontend
npm run test
```

Smoke E2E con backend temporal y seeding determinista:

```bash
cd frontend
npm run test:e2e
```

El E2E levanta:

- `scripts/e2e_backend.py`
- `scripts/seed_e2e_runs.py`
- `vite preview` con `VITE_API_BASE_URL=http://127.0.0.1:8010`

Los runs sembrados cubren:

- run correcto
- wrong file
- retry without adaptation
- same tools, different artifact
- clone sin divergencia observable

Escenarios disponibles en el planner:

- `meetup_plan`
- `weather_gate`
- `budget_only`
- `barcelona_shortlist`

En Windows puedes usar los scripts ya preparados:

```bat
scripts\run_backend_lmstudio.cmd
scripts\run_lmstudio_agent.cmd qwen/qwen3-4b-2507
scripts\run_lmstudio_planner_agent.cmd meetup_plan
```

Para el arnes de E2E:

```bat
python scripts\e2e_backend.py
python scripts\seed_e2e_runs.py
```

## Vistas del visor

Cada run muestra:

- cabecera con estado, duracion, turnos, tools, errores, retries y tokens
- timeline por pasos
- grafo de ejecucion o grafo de decisiones
- tool chain con `call_id`, estado, duracion y resumen
- command chain, file activity y patch activity
- panel "Por que ocurrio" con narrativa y turning points
- evidencia enlazada
- analitica por run con tool graph, coste/latencia y similar runs
- compare workspace de primer nivel con timeline alineado, root cause y diffs de tools, commands, files y artifacts

## Filtros de Similar runs

La UI y el endpoint `GET /api/runs/{id}/analytics` soportan:

- `same_agent_only`
- `status`
- `shared_tools_only`
- `min_score`
- `limit`

Ejemplo:

```text
/api/runs/<run_id>/analytics?same_agent_only=true&shared_tools_only=true&min_score=0.3&limit=8
```

## Compare API

El debugger lado a lado usa:

```text
GET /api/runs/compare?left_run_id=<id>&right_run_id=<id>
```

La respuesta incluye:

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

## Auditoria IA automatizada

El repo incluye un toolkit de auditoria en `scripts/audit` y configuraciones en `audit/`.

Instalacion de dependencias opcionales:

```bash
uv pip install -r audit/requirements.txt
```

Pipelines disponibles:

```bash
make audit-security   # semgrep + bandit
make audit-eval       # DeepEval + Promptfoo
make audit-redteam    # Garak
make audit-drift      # drift sobre historico de runs (Evidently opcional)
make audit-all        # ejecuta todo en secuencia
```

Archivos relevantes:

- `scripts/audit/run_security_scans.py`
- `scripts/audit/run_deepeval_suite.py`
- `scripts/audit/run_promptfoo_regression.py`
- `scripts/audit/run_garak_redteam.py`
- `scripts/audit/run_drift_report.py`
- `scripts/audit/run_all.py`
- `audit/promptfoo/promptfooconfig.yaml`

Los reportes se escriben en `audit/reports/**`.

## Estado actual del MVP

- Python + OpenAI compatible API soportado.
- LM Studio soportado como caso OpenAI-compatible.
- Observabilidad post-run.
- Redaccion basica de datos sensibles en resumentes persistidos.
- Explicacion determinista basada en eventos observables.
- Guardrails configurables para prompt injection, PII y secretos en salida.
- Endpoint de metricas `GET /metrics` para Prometheus.
- Integracion opcional con OpenTelemetry (OTLP).
- Scripts de auditoria continua (Promptfoo, DeepEval, Garak, Semgrep/Bandit, drift).

Quedan fuera en esta version:

- live tracing
- multi-tenant y RBAC
- compatibilidad con apps cerradas tipo desktop UI
