from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: apps/api/app/core/config.py -> ../../../../
REPO_ROOT = Path(__file__).resolve().parents[4]
API_ROOT = Path(__file__).resolve().parents[2]


def _default_db_url() -> str:
    return f"sqlite:///{(REPO_ROOT / 'data' / 'tech_hype.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = _default_db_url()
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_origin: str = "http://localhost:3000"
    log_level: str = "INFO"
    scheduler_enabled: bool = True
    hn_newstories_interval_seconds: int = 120
    hn_topstories_interval_seconds: int = 300
    rss_default_interval_seconds: int = 600
    sources_config_path: str = str(REPO_ROOT / "config" / "sources.yaml")
    logs_dir: str = str(REPO_ROOT / "logs")
    data_dir: str = str(REPO_ROOT / "data")

    @field_validator("database_url", mode="before")
    @classmethod
    def resolve_sqlite_path(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if not value.startswith("sqlite:///"):
            return value
        raw = value.removeprefix("sqlite:///")
        # Keep :memory: and absolute paths as-is.
        if raw == ":memory:" or Path(raw).is_absolute():
            return value
        # Resolve relative DB paths against repo root (not process cwd).
        abs_path = (REPO_ROOT / raw).resolve()
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{abs_path.as_posix()}"


settings = Settings()
