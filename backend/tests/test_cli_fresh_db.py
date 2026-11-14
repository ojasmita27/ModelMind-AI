"""Runs the REAL command-line tools (alembic, check_config) against a brand-new SQLite file."""
import os
import sqlite3
import subprocess
import sys

from tests.conftest import BACKEND_DIR

SECRET = "x" * 40


def run(args, db_path, **extra_env):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}", "SECRET_KEY": SECRET, **extra_env}
    return subprocess.run([sys.executable, *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=180)


def tables(db_path):
    with sqlite3.connect(db_path) as c:
        return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_fresh_sqlite_database_migrates_up_and_down(tmp_path):
    db = tmp_path / "nested" / "fresh_test.db"  # parent folder does not exist yet

    before = run(["-m", "app.check_config"], db)
    assert before.returncode == 1 and "NOT up to date" in before.stdout and "alembic upgrade head" in before.stdout

    up = run(["-m", "alembic", "upgrade", "head"], db)
    assert up.returncode == 0, up.stderr
    assert {"users", "projects", "alembic_version"} <= tables(db)

    after = run(["-m", "app.check_config"], db)
    assert after.returncode == 0, after.stdout + after.stderr
    assert "up to date" in after.stdout and "sqlite" in after.stdout
    assert SECRET not in after.stdout + after.stderr  # secrets never printed

    down = run(["-m", "alembic", "downgrade", "base"], db)
    assert down.returncode == 0, down.stderr
    assert "users" not in tables(db)
    assert run(["-m", "alembic", "upgrade", "head"], db).returncode == 0


def test_sqlite_server_defaults_work_without_python_defaults(tmp_path):
    db = tmp_path / "defaults_test.db"
    assert run(["-m", "alembic", "upgrade", "head"], db).returncode == 0
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO users (id, email, password_hash) VALUES ('u1','a@b.co','h')")
        assert c.execute("SELECT created_at FROM users").fetchone()[0]


def test_invalid_configuration_fails_with_actionable_message_and_no_secret(tmp_path):
    bad_secret = "supersecretvalue"
    for args in (["-m", "app.check_config"], ["-m", "alembic", "current"]):
        r = run(args, tmp_path / "x_test.db", SECRET_KEY=bad_secret)
        out = r.stdout + r.stderr
        assert r.returncode == 2, out
        assert "SECRET_KEY" in out and "configuration is invalid" in out
        assert bad_secret not in out


def test_unreachable_postgres_is_reported_with_hint(tmp_path):
    r = run(["-m", "app.check_config"], tmp_path / "unused_test.db",
            DATABASE_URL="postgresql+psycopg://u:pw-not-printed@127.0.0.1:1/nope")
    out = r.stdout + r.stderr
    assert r.returncode == 1 and "NO" in out and "docker compose up -d postgres" in out
    assert "pw-not-printed" not in out
