"""Provider search helpers shared by enrichment and review."""

from despues_del_susto.config import MetadataSettings, Settings
from despues_del_susto.providers.cache import JsonCache
from despues_del_susto.providers.igdb import IgdbClient
from despues_del_susto.providers.tmdb import TmdbClient
from despues_del_susto.services.matching import (
    ScoredCandidate,
    clean_query,
    score_candidates,
)


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
    query: str,
) -> list[ScoredCandidate]:
    search_query = clean_query(query)
    if not search_query:
        return []
    if type_ == "videogame":
        candidates = igdb.search(search_query)
    else:
        candidates = []
        for language in (settings.metadata_language, "en-US"):
            candidates.extend(
                tmdb.search(search_query, "movie", language=language)
            )
            candidates.extend(tmdb.search(search_query, "tv", language=language))
    return score_candidates(search_query, candidates)
