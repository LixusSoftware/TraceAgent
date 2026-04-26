from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from visor_agentico.api.runs import router as runs_router
from visor_agentico.config import Settings, get_settings
from visor_agentico.db import Base, create_session_factory
from visor_agentico.services.audit_guardrails import AuditGuardrails
from visor_agentico.services.observability import AppObservability, configure_opentelemetry
from visor_agentico.services.provider import OpenAIProviderAdapter


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or get_settings()
    app = FastAPI(title=current_settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=current_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine, session_factory = create_session_factory(current_settings.database_url)
    Base.metadata.create_all(bind=engine)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = current_settings
    app.state.provider_registry = {"openai": OpenAIProviderAdapter(current_settings)}
    app.state.observability = AppObservability(current_settings.audit_metrics_enabled)
    app.state.observability.instrument_app(app)
    app.state.guardrails = AuditGuardrails(current_settings, app.state.observability)
    app.state.otel = configure_opentelemetry(app, current_settings)

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(runs_router)
    return app


app = create_app()
