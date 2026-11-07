"""The ``subs`` step: download automatic subtitles."""

from despues_del_susto.config import Settings
from despues_del_susto.db import session_scope
from despues_del_susto.db.models import Episode
from despues_del_susto.services.processing import get_or_create
from despues_del_susto.steps.subtitles import download_subtitles


def run(episode: Episode, settings: Settings) -> None:
    download = download_subtitles(settings, episode.video_id)
    with session_scope(settings) as session:
        row = get_or_create(session, episode.id)
        row.subtitles_available = download.available
        row.subtitles_language = download.language
        session.commit()
