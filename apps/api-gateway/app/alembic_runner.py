from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def apply_migrations(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
