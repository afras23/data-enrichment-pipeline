"""
Application configuration.

Loads validated settings from environment variables for API, database,
HTTP scraping, OpenAI, quality thresholds, and alerting.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the enrichment pipeline service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="data-enrichment-pipeline", description="Service name")
    app_env: str = Field(default="development", description="development|staging|production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    log_json: bool = Field(
        default=False,
        description="Emit logs as JSON lines (structured logging for production)",
    )

    api_prefix: str = Field(default="/api/v1")

    database_url: str = Field(
        default="postgresql+asyncpg://test:test@localhost:5432/test_db",
        description="Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host:5432/db",
    )
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=50)

    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_timeout_seconds: float = Field(default=120.0, ge=5.0)
    openai_max_tokens: int = Field(default=4096, ge=256)
    openai_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_cost_per_run_usd: float = Field(default=5.0, ge=0.0)
    openai_input_cost_per_million: float = Field(default=0.15, ge=0.0)
    openai_output_cost_per_million: float = Field(default=0.60, ge=0.0)

    http_user_agent: str = Field(
        default="DataEnrichmentBot/1.0 (+https://example.com/bot)",
        description="User-Agent for outbound HTTP fetches",
    )
    http_timeout_seconds: float = Field(default=20.0, ge=1.0)
    http_max_redirects: int = Field(default=5, ge=0, le=20)
    http_max_response_bytes: int = Field(default=2_000_000, ge=10_000)
    max_pages_per_company: int = Field(default=6, ge=1, le=30)
    pipeline_max_concurrency: int = Field(default=3, ge=1, le=20)

    discovery_try_www: bool = Field(default=True, description="Also probe www. host variants")

    quality_pass_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    alert_avg_quality_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    alert_consecutive_failure_threshold: int = Field(default=3, ge=1, le=100)


settings = Settings()
