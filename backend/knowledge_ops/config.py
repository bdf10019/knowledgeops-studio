from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KNOWLEDGEOPS_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "KnowledgeOps Studio"
    environment: str = "local"
    demo_mode: bool = True
    content_root: str = ""
    database_url: str = ""
    redis_url: str = ""
    default_provider: str = "mock"
    upload_limit_bytes: int = 2 * 1024 * 1024
    retrieval_k: int = 4
    min_evidence_score: float = 0.18
    request_timeout_seconds: float = 45.0
    worker_poll_seconds: float = 1.0
    requests_per_minute: int = 60
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    openai_model: str = Field(default="gpt-5.4-mini", validation_alias="OPENAI_MODEL")
    anthropic_model: str = Field(default="claude-sonnet-5", validation_alias="ANTHROPIC_MODEL")
    gemini_model: str = Field(default="gemini-3.7-flash", validation_alias="GEMINI_MODEL")

    @property
    def effective_database_url(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()
        db_path = (PROJECT_ROOT / "data" / "knowledgeops.db").as_posix()
        return f"sqlite:///{db_path}"

    @property
    def effective_content_root(self) -> Path:
        if self.content_root.strip():
            return Path(self.content_root).expanduser().resolve()
        working_directory = Path.cwd()
        if (working_directory / "examples").is_dir():
            return working_directory
        return PROJECT_ROOT

    @property
    def origins(self) -> list[str]:
        return [value.strip() for value in self.allowed_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
