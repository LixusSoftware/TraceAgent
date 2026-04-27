from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Visor Agentico"
    database_url: str = "sqlite:///./visor_agentico.db"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    google_api_key: str | None = None
    kimi_api_key: str | None = None
    kimi_base_url: str | None = None
    lmstudio_base_url: str | None = None
    lmstudio_mode: str = "openai"
    lmstudio_api_key: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    model_pricing: dict[str, dict[str, float]] = Field(default_factory=dict)
    audit_enable_guardrails: bool = False
    audit_fail_on_prompt_injection: bool = False
    audit_enable_pii_anonymization: bool = False
    audit_prompt_injection_threshold: float = 0.85
    audit_pii_entities: list[str] = Field(
        default_factory=lambda: [
            "CREDIT_CARD",
            "CRYPTO",
            "EMAIL_ADDRESS",
            "IBAN_CODE",
            "IP_ADDRESS",
            "PERSON",
            "PHONE_NUMBER",
            "US_SSN",
        ]
    )
    audit_metrics_enabled: bool = True
    audit_enable_otel: bool = False
    audit_otel_service_name: str = "visor-agentico-backend"
    audit_otel_exporter_endpoint: str | None = None
    audit_otel_exporter_protocol: str = "grpc"
    capture_full_payloads: bool = True

    model_config = SettingsConfigDict(
        env_prefix="VISOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
