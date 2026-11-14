from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings
from app.core.startup import format_settings_error, redact_url

KEY = "k" * 40


def make(**kw):
    kw.setdefault("secret_key", KEY)
    return Settings(_env_file=None, **kw)


def test_relative_sqlite_path_resolves_from_project_root_not_cwd():
    s = make(database_url="sqlite:///./data/dev.db")
    assert Path(s.database_url.removeprefix("sqlite:///")) == PROJECT_ROOT / "data" / "dev.db"
    assert s.database_backend == "sqlite"


def test_postgres_url_is_normalized_to_psycopg_driver():
    s = make(database_url="postgresql://u:p@localhost:5432/db")
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.database_backend == "postgresql"


@pytest.mark.parametrize("bad", ["sqlite://", "sqlite:///:memory:", "mysql://u:p@h/db", "not a url", "postgresql+psycopg://u:CHANGE_ME_x@h/db"])
def test_bad_database_urls_rejected(bad):
    with pytest.raises(ValidationError):
        make(database_url=bad)


def test_production_refuses_sqlite():
    with pytest.raises(ValidationError, match="production"):
        make(database_url="sqlite:///./data/x.db", environment="production")


def test_invalid_log_level_and_secret_rejected():
    with pytest.raises(ValidationError):
        make(database_url="sqlite:///./data/x.db", log_level="LOUD")
    with pytest.raises(ValidationError):
        make(database_url="sqlite:///./data/x.db", secret_key="too-short")
    with pytest.raises(ValidationError, match="CHANGE_ME"):
        make(database_url="sqlite:///./data/x.db", secret_key="CHANGE_ME" + "x" * 40)


def test_env_file_with_utf8_bom_is_read(tmp_path, monkeypatch):
    # Windows PowerShell 5.1 / Notepad can write a BOM; the first key must still parse.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    f = tmp_path / ".env"
    f.write_bytes(b"\xef\xbb\xbfDATABASE_URL=sqlite:///./data/bom.db\nSECRET_KEY=" + KEY.encode() + b"\n")
    assert Settings(_env_file=f).database_url.endswith("bom.db")


def test_error_message_names_variables_but_never_values(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError) as missing:
        Settings(_env_file=None, database_url="postgresql+psycopg://u:hunter2pw@h/db")
    text = format_settings_error(missing.value)
    assert "SECRET_KEY is not set" in text and "hunter2pw" not in text

    with pytest.raises(ValidationError) as short:
        Settings(_env_file=None, database_url="sqlite:///./data/x.db", secret_key="my-real-looking-secret")
    text = format_settings_error(short.value)
    assert "SECRET_KEY" in text and "my-real-looking-secret" not in text


def test_redact_url_hides_password():
    assert "hunter2pw" not in redact_url("postgresql+psycopg://u:hunter2pw@h:5432/db")
    assert redact_url("sqlite:///./data/x.db").startswith("sqlite")
