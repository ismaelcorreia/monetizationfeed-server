"""
Centralised configuration — loaded once, injected everywhere.
All values sourced from environment variables with safe defaults.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Procura o .env na raiz do projeto (uma pasta acima de 'src')
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = field(default_factory=lambda: os.getenv("POSTGRES_HOST", "postgres"))
    port: int = field(default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")))
    name: str = field(default_factory=lambda: os.getenv("POSTGRES_DB", "newsdb"))
    user: str = field(default_factory=lambda: os.getenv("POSTGRES_USER", "newsuser"))
    password: str = field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "newspass"))

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass(frozen=True)
class MinioConfig:
    endpoint: str = field(default_factory=lambda: os.getenv("MINIO_ENDPOINT", "minio:9000"))
    access_key: str = field(default_factory=lambda: os.getenv("MINIO_ACCESS_KEY", "minioadmin"))
    secret_key: str = field(default_factory=lambda: os.getenv("MINIO_SECRET_KEY", "minioadmin"))
    secure: bool = field(default_factory=lambda: os.getenv("MINIO_SECURE", "false").lower() == "true")
    media_bucket_prefix: str = "news-media"


@dataclass(frozen=True)
class AIConfig:
    # Provider: 'google' (AI Studio/Gemini), 'openrouter', ou 'ollama' (local)
    provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "ollama"))

    # Google AI Studio (Gemini)
    google_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))

    # Groq
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))

    # Ollama (local) — mantido para compatibilidade e produção
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"))

    # OpenRouter
    openrouter_base_url: str = field(default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api"))
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))

    # Modelo (shared): adaptar conforme o provider
    # Google  → ex: 'gemini-2.0-flash'
    # Ollama  → ex: 'mistral:7b'
    # OpenRouter → ex: 'mistralai/mistral-7b-instruct'
    model: str = field(default_factory=lambda: os.getenv("AI_MODEL", "gemini-2.0-flash"))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("AI_MAX_TOKENS", "4096")))
    request_timeout: int = field(default_factory=lambda: int(os.getenv("AI_TIMEOUT", "120")))
    target_language: str = "pt"


@dataclass(frozen=True)
class SchedulerConfig:
    ingestion_cron: str = field(default_factory=lambda: os.getenv("INGESTION_CRON", "0 6 * * *"))
    discovery_cron: str = field(default_factory=lambda: os.getenv("DISCOVERY_CRON", "0 2 * * 0"))
    ai_processing_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("AI_PROCESSING_INTERVAL", "300"))
    )


@dataclass(frozen=True)
class AppConfig:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    minio: MinioConfig = field(default_factory=MinioConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    discovery_search_terms: list[str] = field(
        default_factory=lambda: os.getenv(
            "DISCOVERY_TERMS",
            "Angola notícias,Africa business news,global economy news,technology news Africa"
        ).split(",")
    )


def load_config() -> AppConfig:
    return AppConfig()