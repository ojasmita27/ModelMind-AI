from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from app.core.startup import load_settings_or_exit
from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.base import Base
from app.db.session import build_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
DATABASE_URL = load_settings_or_exit().database_url
IS_SQLITE = DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True, render_as_batch=IS_SQLITE
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = build_engine(DATABASE_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        # render_as_batch lets future ALTER TABLE migrations work on SQLite too.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=IS_SQLITE)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
