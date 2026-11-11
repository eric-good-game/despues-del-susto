"""TMDB: movies and series."""

import json

import requests

from despues_del_susto.config import MetadataSettings, Settings
from despues_del_susto.providers.base import ProviderError, request_json
from despues_del_susto.providers.cache import JsonCache
from despues_del_susto.providers.models import Candidate

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_URL = "https://image.tmdb.org/t/p/w500"


class TmdbClient:
    def __init__(
        self, settings: Settings, metadata: MetadataSettings, cache: JsonCache
    ) -> None:
        self.settings = settings
        self.token = metadata.tmdb_token.strip()
        self.cache = cache
        self.session = requests.Session()

    def search(
        self, query: str, media_type: str, *, language: str | None = None
    ) -> list[Candidate]:
        """Search a movie or a series. ``media_type`` is ``movie`` or ``tv``."""
        if not self.token:
            raise ProviderError("TMDB_TOKEN is not set")
        path = f"/search/{media_type}"
        params = {
            "query": query,
            "language": language or self.settings.metadata_language,
            "include_adult": "false",
        }
        data = self._get(path, params)
        results = data.get("results", []) if isinstance(data, dict) else []
        return [
            candidate
            for item in results
            if (candidate := self._candidate(item, media_type)) is not None
        ]

    def details(self, media_type: str, external_id: str) -> Candidate:
        if not self.token:
            raise ProviderError("TMDB_TOKEN is not set")
        data = self._get(
            f"/{media_type}/{external_id}",
            {"language": self.settings.metadata_language},
        )
        if not isinstance(data, dict):
            raise ProviderError("invalid TMDB details response")
        candidate = self._candidate(data, media_type)
        if candidate is None:
            raise ProviderError("TMDB details response has no usable title")
        return candidate

    def _get(self, path: str, params: dict) -> object:
        key = f"tmdb:{path}:{json.dumps(params, sort_keys=True)}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        data = request_json(
            self.session,
            "GET",
            BASE_URL + path,
            params=params,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
            timeout=self.settings.metadata_timeout_s,
        )
        self.cache.set(key, data)
        return data

    def _candidate(self, item: dict, media_type: str) -> Candidate | None:
        external_id = item.get("id")
        if external_id is None:
            return None
        is_movie = media_type == "movie"
        title = item.get("title") if is_movie else item.get("name")
        original = (
            item.get("original_title") if is_movie else item.get("original_name")
        )
        date = item.get("release_date") if is_movie else item.get("first_air_date")
        if not title:
            return None
        return Candidate(
            source="TMDB",
            type="movie" if is_movie else "series",
            external_id=str(external_id),
            title=str(title),
            original_title=str(original) if original else None,
            year=_year(date),
            image_url=(
                f"{IMAGE_URL}{item['poster_path']}"
                if item.get("poster_path")
                else None
            ),
            description=item.get("overview") or None,
            source_url=(
                f"https://www.themoviedb.org/{'movie' if is_movie else 'tv'}/"
                f"{external_id}"
            ),
            genres=tuple(
                genre.get("name", "")
                for genre in item.get("genres", [])
                if genre.get("name")
            ),
            popularity=float(item.get("popularity") or 0.0),
            original_language=item.get("original_language") or None,
            origin_country=_first_country(item.get("origin_country")),
        )


def _first_country(value: object) -> str | None:
    if isinstance(value, list) and value and isinstance(value[0], str):
        return value[0]
    return None


def _year(date: object) -> int | None:
    if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    return None
