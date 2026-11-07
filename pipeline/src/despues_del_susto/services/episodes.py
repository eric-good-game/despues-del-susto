"""Episode registration and status queries."""

from dataclasses import dataclass

from sqlalchemy import select

from despues_del_susto.config import Settings
from despues_del_susto.db import Episode, ensure_schema, session_scope
from despues_del_susto.steps import STEPS


class DuplicateEpisodeError(RuntimeError):
    """An episode with that ``video_id`` already exists."""


@dataclass(frozen=True)
class EpisodeStatus:
    video_id: str
    title: str
    availability: str
    steps_done: int
    steps_total: int
    state: str
    error: str | None


def add_episode(settings: Settings, video_id: str, title: str) -> Episode:
    """Register one episode manually, without touching the network."""
    video_id = video_id.strip()
    if not video_id:
        raise ValueError("video_id must not be empty")
    ensure_schema(settings)
    with session_scope(settings) as session:
        existing = session.scalar(select(Episode).where(Episode.video_id == video_id))
        if existing is not None:
            raise DuplicateEpisodeError(f"episode {video_id} already exists")
        episode = Episode(video_id=video_id, title=title.strip())
        session.add(episode)
        session.commit()
        return episode


def list_status(settings: Settings) -> list[EpisodeStatus]:
    """Return one status row per episode, in playlist order."""
    ensure_schema(settings)
    with session_scope(settings) as session:
        episodes = session.scalars(
            select(Episode).order_by(
                Episode.playlist_position.is_(None),
                Episode.playlist_position,
                Episode.id,
            )
        ).all()
        return [_status_for(episode) for episode in episodes]


def _status_for(episode: Episode) -> EpisodeStatus:
    steps = {step.step: step for step in episode.steps}
    done = sum(1 for step in steps.values() if step.status == "done")
    failed = next((step for step in steps.values() if step.status == "failed"), None)

    if not steps:
        state = "not started"
    elif failed is not None:
        state = "failed"
    elif done == len(STEPS):
        state = "complete"
    else:
        state = "in progress"

    return EpisodeStatus(
        video_id=episode.video_id,
        title=episode.title,
        availability=episode.availability,
        steps_done=done,
        steps_total=len(STEPS),
        state=state,
        error=failed.error if failed is not None else None,
    )
