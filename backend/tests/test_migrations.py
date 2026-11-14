from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.db.session import get_engine
from tests.conftest import alembic_config


def test_schema_matches_migration():
    insp = inspect(get_engine())
    assert {"users", "projects", "alembic_version"} <= set(insp.get_table_names())
    assert {c["name"] for c in insp.get_columns("users")} == {"id", "email", "password_hash", "created_at"}
    assert {c["name"] for c in insp.get_columns("projects")} == {
        "id", "owner_id", "name", "description", "created_at", "updated_at",
    }
    assert any(u["column_names"] == ["email"] for u in insp.get_unique_constraints("users"))
    assert any(i["column_names"] == ["owner_id"] for i in insp.get_indexes("projects"))


def test_downgrade_then_upgrade_roundtrip():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    assert "users" not in inspect(get_engine()).get_table_names()
    command.upgrade(cfg, "head")
    insp = inspect(get_engine())
    assert {"users", "projects", "datasets", "dataset_versions", "experiments"} <= set(insp.get_table_names())
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == head
