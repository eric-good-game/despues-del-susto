"""IGDB: videogames, authenticated through Twitch."""

import time
from datetime import UTC, datetime

import requests

from despues_del_susto.config import MetadataSettings, Settings
from despues_del_susto.providers.base import ProviderError, request_json
from despues_del_susto.providers.cache import JsonCache
from despues_del_susto.providers.models import Candidate

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
GAMES_URL = "https://api.igdb.com/v4/games"
IMAGE_URL = "https://images.igdb.com/igdb/image/upload"


class IgdbClient:
    def __init__(
        self, settings: Settings, metadata: MetadataSettings, cache: JsonCache
    ) -> None:
        self.settings = settings
        self.client_id = metadata.twitch_client_id.strip()
        self.client_secret = metadata.twitch_client_secret.strip()
        self.cache = cache
        self.session = requests.Session()
        self._token = ""
        self._expires_at = 0.0

    def search(self, query: str) -> list[Candidate]:
        if not self.client_id or not self.client_secret:
            raise ProviderError("TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET is not set")

        key = f"igdb:search:{query}"
        cached = self.cache.get(key)
        if cached is not None:
            return [candidate for item in cached if (candidate := self._candidate(item))]

        token = self._access_token()
        body = (
            f'search "{_escape(query)}"; '
            "fields name, first_release_date, cover.url, summary, url, "
            "genres.name, rating, aggregated_rating; "
            "limit 10;"
        )
        time.sleep(self.settings.igdb_delay_s)
        data = request_json(
            self.session,
            "POST",
            GAMES_URL,
            headers={
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            data=body,
            timeout=self.settings.metadata_timeout_s,
        )
        if not isinstance(data, list):
            raise ProviderError("invalid IGDB response")
        self.cache.set(key, data)
        return [candidate for item in data if (candidate := self._candidate(item))]

    def _access_token(self) -> str:
        if self._token and time.monotonic() < self._expires_at - 60:
            return self._token
        data = request_json(
            self.session,
            "POST",
            TOKEN_URL,
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=self.settings.metadata_timeout_s,
        )
        if not isinstance(data, dict) or not data.get("access_token"):
            raise ProviderError("invalid Twitch token response")
        self._token = str(data["access_token"])
        self._expires_at = time.monotonic() + int(data.get("expires_in", 3600))
        return self._token

    def _candidate(self, item: dict) -> Candidate | None:
        external_id = item.get("id")
        name = item.get("name")
        if external_id is None or not name:
            return None
        return Candidate(
            source="IGDB",
            type="videogame",
            external_id=str(external_id),
            title=str(name),
            original_title=None,
            year=_year(item.get("first_release_date")),
            image_url=_cover(item.get("cover")),
            description=item.get("summary") or None,
            source_url=item.get("url") or None,
            genres=tuple(
                genre.get("name", "")
                for genre in item.get("genres", [])
                if genre.get("name")
            ),
            popularity=float(
                item.get("rating") or item.get("aggregated_rating") or 0.0
            ),
        )


def _escape(query: str) -> str:
    return query.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _year(timestamp: object) -> int | None:
    if isinstance(timestamp, int | float):
        return datetime.fromtimestamp(timestamp, UTC).year
    return None


def _cover(cover: object) -> str | None:
    if not isinstance(cover, dict):
        return None
    url = cover.get("url")
    if not isinstance(url, str):
        return None
    return f"https:{url}".replace("t_thumb", "t_cover_big")
