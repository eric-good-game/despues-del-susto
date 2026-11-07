import logging

from despues_del_susto.log import configure_logging


def test_http_and_migration_loggers_are_quiet() -> None:
    configure_logging()

    for name in ("alembic", "httpx", "httpx2", "openai"):
        assert logging.getLogger(name).level == logging.WARNING
