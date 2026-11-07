"""Logging setup for the command-line interface."""

import logging as stdlib_logging

_FORMAT = "%(levelname)s %(name)s: %(message)s"


def configure_logging(level: str = "INFO", verbose: bool = False) -> None:
    """Configure root logging once, at the level the command asked for."""
    effective = "DEBUG" if verbose else level.upper()
    stdlib_logging.basicConfig(level=effective, format=_FORMAT)
    # Routine lines from migrations and HTTP clients are noise in the CLI.
    for noisy in ("alembic", "httpx", "httpx2", "openai"):
        stdlib_logging.getLogger(noisy).setLevel(stdlib_logging.WARNING)

