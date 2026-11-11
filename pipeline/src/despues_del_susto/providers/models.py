"""Shared candidate model for TMDB and IGDB."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    source: str
    type: str
    external_id: str
    title: str
    original_title: str | None
    year: int | None
    image_url: str | None
    description: str | None
    source_url: str | None
    genres: tuple[str, ...] = ()
    popularity: float = 0.0
    original_language: str | None = None
    origin_country: str | None = None
