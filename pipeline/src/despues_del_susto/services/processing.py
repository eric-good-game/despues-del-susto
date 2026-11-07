"""Access to the per-episode data produced by the steps."""

from sqlalchemy.orm import Session

from despues_del_susto.db.models import EpisodeProcessing


def get_or_create(session: Session, episode_id: int) -> EpisodeProcessing:
    """Return the processing row for an episode, creating it when missing."""
    row = session.get(EpisodeProcessing, episode_id)
    if row is None:
        row = EpisodeProcessing(episode_id=episode_id, subtitles_available=False)
        session.add(row)
        session.flush()
    return row
