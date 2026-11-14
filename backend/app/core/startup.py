"""Startup helpers: friendly configuration errors and database diagnostics.

Nothing here ever prints secret values: only variable names, problem descriptions and
credential-redacted database targets.
"""
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import PROJECT_ROOT, Settings, get_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


def redact_url(url: str) -> str:
    """Database URL with the password hidden, safe to print and log."""
    return make_url(url).render_as_string(hide_password=True)


def format_settings_error(exc: ValidationError) -> str:
    lines = ["ModelMind cannot start: the configuration is invalid.", ""]
    for err in exc.errors():
        name = str(err["loc"][0]).upper() if err["loc"] else "SETTINGS"
        if err["type"] == "missing":
            lines.append(f"  - {name} is not set.")
        else:  # err["input"] is deliberately never printed: it may be a secret
            msg = str(err["msg"]).removeprefix("Value error, ")
            lines.append(f"  - {name}: {msg}")
    lines.append("")
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        lines.append(f"No .env file found at: {env_file}")
        lines.append("Create one from the template (PowerShell, in the project root):")
        lines.append("    Copy-Item .env.example .env")
    else:
        lines.append(f"Fix the values in: {env_file}  (see .env.example for the expected format)")
    return "\n".join(lines)


def load_settings_or_exit() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        print(format_settings_error(exc), file=sys.stderr)
        raise SystemExit(2) from None


@dataclass
class DbDiagnosis:
    backend: str
    target: str
    reachable: bool
    hint: Optional[str] = None
    current_revision: Optional[str] = None
    head_revision: Optional[str] = None

    @property
    def migrations_current(self) -> Optional[bool]:
        if not self.reachable or self.head_revision is None:
            return None
        return self.current_revision == self.head_revision


def _connection_hint(backend: str) -> str:
    if backend == "sqlite":
        return "Check that DATABASE_URL points to a folder you can write to."
    return (
        "Is PostgreSQL running? Start it with: docker compose up -d postgres "
        "(Docker Desktop must be running), or switch to SQLite mode in .env. "
        "Also check the user, password and port in DATABASE_URL."
    )


def diagnose_database(settings: Optional[Settings] = None) -> DbDiagnosis:
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from app.db.session import get_engine

    settings = settings or get_settings()
    diag = DbDiagnosis(
        backend=settings.database_backend, target=redact_url(settings.database_url), reachable=False
    )
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            diag.reachable = True
            diag.current_revision = MigrationContext.configure(conn).get_current_revision()
    except Exception as exc:  # report the error class only; messages can contain connection details
        diag.hint = f"{type(exc).__name__}. {_connection_hint(diag.backend)}"
        return diag
    try:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        diag.head_revision = ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:
        diag.head_revision = None
    if diag.migrations_current is False:
        diag.hint = "Database tables are missing or outdated. Run (in the backend folder): alembic upgrade head"
    return diag
