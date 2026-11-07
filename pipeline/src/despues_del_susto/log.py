"""Logging setup for the command-line interface."""

import logging as stdlib_logging

_FORMAT = "%(levelname)s %(name)s: %(message)s"


def configure_logging(level: str = "INFO", verbose: bool = False) -> None:
    """Configure root logging once, at the level the command asked for."""
    effective = "DEBUG" if verbose else level.upper()
    stdlib_logging.basicConfig(level=effective, format=_FORMAT)
    # Migrations run on every command; their routine INFO lines are noise.
    stdlib_logging.getLogger("alembic").setLevel(stdlib_logging.WARNING)

