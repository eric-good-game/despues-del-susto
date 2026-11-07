"""Discover episodes in the podcast playlist.

Phase 1 only validates configuration. The real discovery, based on
``yt-dlp --flat-playlist`` and upserts by ``video_id``, arrives in phase 2.
"""

from despues_del_susto.config import Settings
from despues_del_susto.db import Episode


class DiscoveryNotConfigured(RuntimeError):
    """Neither the option nor the environment provides a playlist URL."""


def sync_playlist(settings: Settings, playlist_url: str | None = None) -> list[Episode]:
    url = playlist_url or settings.playlist_url
    if not url:
        raise DiscoveryNotConfigured(
            "no playlist configured; set DDS_PLAYLIST_URL or pass --playlist-url"
        )
    raise NotImplementedError("episode discovery is implemented in phase 2")
