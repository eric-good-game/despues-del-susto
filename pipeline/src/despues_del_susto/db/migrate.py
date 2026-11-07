"""Apply schema migrations to the local database."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from despues_del_susto.config import Settings


def _alembic_config(settings: Settings) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def ensure_schema(settings: Settings) -> None:
    """Create the data directory and bring the database up to the latest revision."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(settings), "head")
