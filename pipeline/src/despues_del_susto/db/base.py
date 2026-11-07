"""Declarative base for the local database."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for every ORM model."""
