"""Provider search helpers shared by enrichment and review."""

from despues_del_susto.config import MetadataSettings, Settings
from despues_del_susto.providers.cache import JsonCache
from despues_del_susto.providers.igdb import IgdbClient
from despues_del_susto.providers.tmdb import TmdbClient
from despues_del_susto.services.matching import ScoredCandidate
from despues_del_susto.services.matching_enhanced import enhanced_search_candidates


def make_clients(settings: Settings) -> tuple[TmdbClient, IgdbClient]:
    metadata = MetadataSettings()
    cache = JsonCache(settings.data_dir / "cache")
    return (
        TmdbClient(settings, metadata, cache),
        IgdbClient(settings, metadata, cache),
    )


def search_candidates(
    settings: Settings,
    tmdb: TmdbClient,
    igdb: IgdbClient,
    type_: str,
    queries: list[tuple[str, str]],
) -> list[ScoredCandidate]:
    return enhanced_search_candidates(settings, tmdb, igdb, type_, queries)
