"""Database connections."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from despues_del_susto.config import Settings


def _enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(settings: Settings) -> Engine:
    """Create an engine for the configured database, with foreign keys enabled."""
    engine = create_engine(settings.database_url)
    event.listen(engine, "connect", _enable_foreign_keys)
    return engine


@contextmanager
def session_scope(settings: Settings) -> Iterator[Session]:
    """Open a session and close it, disposing of the engine afterwards."""
    engine = make_engine(settings)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as session:
            yield session
    finally:
        engine.dispose()
