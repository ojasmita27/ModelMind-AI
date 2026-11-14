"""Test harness.

SAFETY: tests NEVER touch your development database.

* Default: every test session uses a brand-new SQLite file in the system temp folder.
* Optional: set TEST_DATABASE_URL to a PostgreSQL URL whose database name ends with "_test"
  to run the same suite against PostgreSQL. Anything else is refused.

The schema is always built by running the real Alembic migrations, so migrations are exercised
on every test run.
"""
import os
import shutil
import tempfile
import time
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
_dotenv_file = PROJECT_ROOT / ".env"
_dotenv = dotenv_values(_dotenv_file, encoding="utf-8-sig") if _dotenv_file.exists() else {}

TEST_TMP_DIR = Path(tempfile.mkdtemp(prefix="modelmind_tests_"))
_requested = os.environ.get("TEST_DATABASE_URL") or _dotenv.get("TEST_DATABASE_URL")
TEST_DATABASE_URL = _requested or f"sqlite:///{(TEST_TMP_DIR / 'test.db').as_posix()}"


def _guard(url_str: str) -> None:
    url = make_url(url_str)
    configured_main = os.environ.get("DATABASE_URL") or _dotenv.get("DATABASE_URL")
    if configured_main and make_url(configured_main).render_as_string(hide_password=False) == url.render_as_string(hide_password=False):
        raise RuntimeError("TEST_DATABASE_URL equals DATABASE_URL. Refusing to run tests on your real database.")
    backend = url.get_backend_name()
    if backend == "postgresql":
        if not (url.database or "").endswith("_test"):
            raise RuntimeError("TEST_DATABASE_URL must name a PostgreSQL database ending in '_test'.")
    elif backend == "sqlite":
        if "test" not in Path(url.database or "").name.lower():
            raise RuntimeError("A SQLite TEST_DATABASE_URL must use a file name containing 'test'.")
    else:
        raise RuntimeError(f"Unsupported test database: {backend}")


_guard(TEST_DATABASE_URL)

# Must be set BEFORE the app is imported. Real environment variables beat the .env file.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-test-secret-key"
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["LOG_FORMAT"] = "text"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import get_engine  # noqa: E402
from app.main import create_app  # noqa: E402


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


@pytest.fixture(scope="session", autouse=True)
def _database():
    engine = get_engine()
    if engine.dialect.name == "postgresql":  # reset a reused *_test database
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield
    engine.dispose()
    shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    # Let in-flight background jobs finish BEFORE deleting rows; otherwise a
    # worker updating an experiment/dataset version hits StaleDataError on a
    # row the cascade already removed, and its writes can leak into the next
    # test. Bounded so a genuinely stuck job cannot hang the suite forever.
    try:
        from app.jobs import get_job_queue

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not get_job_queue().idle():
            time.sleep(0.05)
    except Exception:
        pass
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM projects"))
        conn.execute(text("DELETE FROM users"))


@pytest.fixture(scope="session")
def client():
    with TestClient(create_app()) as c:
        yield c


def _register_and_login(client: TestClient, email: str, password: str = "correct-horse-battery") -> dict:
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def alice(client):
    return _register_and_login(client, "alice@example.com")


@pytest.fixture
def bob(client):
    return _register_and_login(client, "bob@example.com")


def pytest_report_header(config):
    return f"modelmind test database: {make_url(TEST_DATABASE_URL).render_as_string(hide_password=True)}"
