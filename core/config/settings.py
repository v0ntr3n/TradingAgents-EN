"""Unified Pydantic v2 Settings Hierarchy (`core/config/settings.py`)."""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """Database connection settings for MongoDB and Redis."""

    mongodb_host: str = Field(default="localhost")
    mongodb_port: int = Field(default=27017)
    mongodb_username: str = Field(default="")
    mongodb_password: str = Field(default="")
    mongodb_database: str = Field(default="tradingagents")
    mongodb_auth_source: str = Field(default="admin")
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: str = Field(default="")
    redis_db: int = Field(default=0)

    @property
    def mongo_uri(self) -> str:
        if self.mongodb_username and self.mongodb_password:
            return (
                f"mongodb://{self.mongodb_username}:{self.mongodb_password}"
                f"@{self.mongodb_host}:{self.mongodb_port}/{self.mongodb_database}"
                f"?authSource={self.mongodb_auth_source}"
            )
        return f"mongodb://{self.mongodb_host}:{self.mongodb_port}/{self.mongodb_database}"

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


class LLMProviderSettings(BaseModel):
    """LLM provider and default model configuration."""

    default_provider: str = Field(default="deepseek")
    quick_think_llm: str = Field(default="deepseek-chat")
    deep_think_llm: str = Field(default="deepseek-reasoner")
    request_timeout_seconds: int = Field(default=120)
    max_retries: int = Field(default=3)
    models_registry_path: str = Field(default="configs/models_registry.yaml")


class DataSourceSettings(BaseModel):
    """Market data source priorities and cache configuration."""

    default_china_source: str = Field(default="akshare")
    default_us_source: str = Field(default="yfinance")
    enable_cache: bool = Field(default=True)
    cache_ttl_seconds: int = Field(default=3600)
    data_dir: str = Field(default="./data")


class AgentRuntimeSettings(BaseModel):
    """CARE-Agents coordination, CBS debate gating, and Regime-MWU parameters."""

    max_debate_rounds: int = Field(default=2)
    max_risk_discuss_rounds: int = Field(default=1)
    cbs_friction_bps_cn: float = Field(default=15.0)
    cbs_friction_bps_us: float = Field(default=5.0)
    mwu_eta: float = Field(default=0.35)
    mwu_gamma_shrinkage: float = Field(default=0.05)
    drawdown_circuit_breaker_floor: float = Field(default=0.068)


class LoggingSettings(BaseModel):
    """Application logging settings."""

    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/tradingagents.log")
    log_format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class AppSettings(BaseSettings):
    """Single canonical application settings object backed by environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    debug: bool = Field(default=True, alias="DEBUG")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    timezone: str = Field(default="Asia/Shanghai", alias="TIMEZONE")
    jwt_secret: str = Field(default="change-me-in-production", alias="JWT_SECRET")
    allowed_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    llm: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    datasource: DataSourceSettings = Field(default_factory=DataSourceSettings)
    agent_runtime: AgentRuntimeSettings = Field(default_factory=AgentRuntimeSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached unified AppSettings instance."""
    return AppSettings()
