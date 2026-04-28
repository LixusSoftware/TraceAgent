from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request, Response

from trace_agent_server.config import Settings


class AppObservability:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._registry = None
        self._http_requests_total = None
        self._http_request_duration_seconds = None
        self._guardrail_findings_total = None
        self._guardrail_blocked_total = None

        if not enabled:
            return

        try:
            from prometheus_client import CollectorRegistry, Counter, Histogram

            self._registry = CollectorRegistry()
            self._http_requests_total = Counter(
                "trace_agent_http_requests_total",
                "Total HTTP requests processed by the backend.",
                ["method", "path", "status_code"],
                registry=self._registry,
            )
            self._http_request_duration_seconds = Histogram(
                "trace_agent_http_request_duration_seconds",
                "HTTP request latency in seconds.",
                ["method", "path"],
                registry=self._registry,
                buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
            )
            self._guardrail_findings_total = Counter(
                "trace_agent_guardrail_findings_total",
                "Total guardrail findings.",
                ["kind", "severity"],
                registry=self._registry,
            )
            self._guardrail_blocked_total = Counter(
                "trace_agent_guardrail_blocked_total",
                "Total blocked requests due to guardrails.",
                ["reason"],
                registry=self._registry,
            )
        except Exception:
            self.enabled = False

    def instrument_app(self, app: FastAPI, metrics_path: str = "/metrics") -> None:
        if not self.enabled:
            return

        @app.middleware("http")
        async def _metrics_middleware(request: Request, call_next):
            started = time.perf_counter()
            status_code = 500
            try:
                response = await call_next(request)
                status_code = response.status_code
                return response
            finally:
                route_path = self._route_path(request)
                elapsed = max(0.0, time.perf_counter() - started)
                if self._http_requests_total is not None:
                    self._http_requests_total.labels(request.method, route_path, str(status_code)).inc()
                if self._http_request_duration_seconds is not None:
                    self._http_request_duration_seconds.labels(request.method, route_path).observe(elapsed)

        @app.get(metrics_path)
        def _metrics() -> Response:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            payload = generate_latest(self._registry)
            return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    def record_guardrail_finding(self, *, kind: str, severity: str) -> None:
        if not self.enabled or self._guardrail_findings_total is None:
            return
        self._guardrail_findings_total.labels(kind, severity).inc()

    def record_guardrail_block(self, reason: str) -> None:
        if not self.enabled or self._guardrail_blocked_total is None:
            return
        self._guardrail_blocked_total.labels(reason).inc()

    @staticmethod
    def _route_path(request: Request) -> str:
        route = request.scope.get("route")
        if route is not None and hasattr(route, "path"):
            return str(route.path)
        return request.url.path


def configure_opentelemetry(app: FastAPI, settings: Settings) -> dict[str, Any]:
    if not settings.audit_enable_otel:
        return {"enabled": False, "reason": "disabled"}

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:
        return {"enabled": False, "reason": f"missing_dependencies:{exc}"}

    exporter = None
    protocol = settings.audit_otel_exporter_protocol.lower().strip()
    endpoint = settings.audit_otel_exporter_endpoint

    try:
        if protocol == "http":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True) if endpoint else OTLPSpanExporter(insecure=True)
    except Exception as exc:
        return {"enabled": False, "reason": f"exporter_init_failed:{exc}"}

    resource = Resource(attributes={SERVICE_NAME: settings.audit_otel_service_name})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(tracer_provider)
    FastAPIInstrumentor.instrument_app(app)

    return {
        "enabled": True,
        "service_name": settings.audit_otel_service_name,
        "protocol": protocol,
        "endpoint": endpoint,
    }
