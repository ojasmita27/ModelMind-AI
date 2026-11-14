from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# backend/app/core/config.py -> project root is three levels above this file's folder
PROJECT_ROOT = Path(__file__).resolve().parents[3]

_DB_EXAMPLES = (
    "Examples: sqlite:///./data/modelmind_dev.db  or  "
    "postgresql+psycopg://user:password@localhost:5432/modelmind"
)


class Settings(BaseSettings):
    """Application settings, read from environment variables or the root .env file.

    Real environment variables take priority over the .env file.
    ``utf-8-sig`` makes a Notepad-style UTF-8 BOM harmless.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    app_name: str = "ModelMind AI"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"
    max_dataset_size_mb: int = Field(default=100, gt=0)
    allowed_dataset_extensions: list[str] = [".csv"]

    @field_validator("secret_key")
    @classmethod
    def _reject_placeholder_secret(cls, value: str) -> str:
        if "CHANGE_ME" in value:
            raise ValueError(
                "still contains the CHANGE_ME placeholder. Generate a real one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return level

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        raw = value.strip()
        if "CHANGE_ME" in raw:
            raise ValueError("still contains the CHANGE_ME placeholder. Put your real database password in it.")
        for prefix in ("postgresql://", "postgres://"):
            if raw.startswith(prefix):
                raw = "postgresql+psycopg://" + raw[len(prefix):]
        try:
            url = make_url(raw)
        except ArgumentError:
            raise ValueError(f"is not a valid database URL. {_DB_EXAMPLES}") from None

        backend = url.get_backend_name()
        if backend == "sqlite":
            if not url.database or url.database == ":memory:":
                raise ValueError(
                    "must point to a SQLite file, not memory (each connection would get an empty "
                    "database). Example: sqlite:///./data/modelmind_dev.db"
                )
            path = Path(url.database)
            if not path.is_absolute():  # relative paths resolve from the project root, not the cwd
                path = PROJECT_ROOT / path
            url = url.set(database=str(path))
        elif backend == "postgresql":
            if url.drivername != "postgresql+psycopg":
                raise ValueError("must use the psycopg v3 driver: postgresql+psycopg://...")
        else:
            raise ValueError(f"uses unsupported database '{backend}'. {_DB_EXAMPLES}")
        return url.render_as_string(hide_password=False)

    @model_validator(mode="after")
    def _no_sqlite_in_production(self) -> "Settings":
        if self.environment == "production" and self.database_backend == "sqlite":
            raise ValueError("ENVIRONMENT=production cannot use SQLite. Use PostgreSQL.")
        return self

    @property
    def database_backend(self) -> str:
        return make_url(self.database_url).get_backend_name()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
