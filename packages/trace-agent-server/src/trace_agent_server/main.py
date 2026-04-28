from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trace_agent_server.api.runs import router as runs_router
from trace_agent_server.config import Settings, get_settings
from trace_agent_server.db import Base, create_session_factory
from trace_agent_server.services.audit_guardrails import AuditGuardrails
from trace_agent_server.services.observability import AppObservability, configure_opentelemetry
from trace_agent_server.services.provider import (
    AnthropicProviderAdapter,
    BaseProviderAdapter,
    GoogleProviderAdapter,
    KimiProviderAdapter,
    LMStudioProviderAdapter,
    OpenAIProviderAdapter,
)


def build_provider_registry(settings: Settings) -> dict[str, BaseProviderAdapter]:
    """Dynamically instantiate provider adapters based on available configuration."""
    registry: dict[str, BaseProviderAdapter] = {}

    # OpenAI is always registered (it can work with just a base_url for local proxies)
    registry["openai"] = OpenAIProviderAdapter(settings)

    if settings.anthropic_api_key or settings.anthropic_base_url:
        registry["anthropic"] = AnthropicProviderAdapter(settings)

    if settings.google_api_key:
        registry["google"] = GoogleProviderAdapter(settings)

    if settings.kimi_api_key or settings.kimi_base_url:
        registry["kimi"] = KimiProviderAdapter(settings)

    if settings.lmstudio_base_url:
        registry["lmstudio"] = LMStudioProviderAdapter(settings)

    return registry


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
    app.state.provider_registry = build_provider_registry(current_settings)
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
