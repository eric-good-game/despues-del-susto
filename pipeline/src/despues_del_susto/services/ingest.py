"""Run the pipeline for one episode or for a batch of pending episodes."""

from dataclasses import dataclass
from time import monotonic

from sqlalchemy import select

from despues_del_susto.config import Settings
from despues_del_susto.db import Episode, ProcessingStep, ensure_schema, session_scope
from despues_del_susto.db.models import utcnow
from despues_del_susto.progress import ProgressSink
from despues_del_susto.steps import (
    STEPS,
    StepNotImplemented,
    StopBatch,
    is_implemented,
    run_step,
    target_step,
)


class UnknownEpisodeError(RuntimeError):
    """The requested episode is not registered."""


class UnknownStepError(RuntimeError):
    """The step name does not exist."""


@dataclass(frozen=True)
class StepOutcome:
    step: str
    status: str  # done | skipped | failed | not_implemented | stopped
    detail: str = ""
    stop_batch: bool = False


def ingest_episode(
    settings: Settings,
    video_id: str,
    *,
    redo: str | None = None,
    progress: ProgressSink | None = None,
) -> list[StepOutcome]:
    """Run every step for one episode, skipping the ones already done.

    Steps run in order and stop at the first failure, so a retry resumes from
    the failed step instead of repeating finished work. ``redo`` resets that step
    and every step after it, because their output depends on it.
    """
    progress = progress or ProgressSink()
    ensure_schema(settings)
    with session_scope(settings) as session:
        episode = session.scalar(select(Episode).where(Episode.video_id == video_id))
        if episode is None:
            raise UnknownEpisodeError(
                f"episode {video_id} is not registered; add it with "
                f"`dds episode add {video_id} --title \"...\"`"
            )

        existing = {step.step: step for step in episode.steps}
        for name in STEPS:
            if name not in existing:
                session.add(ProcessingStep(episode_id=episode.id, step=name))
        session.commit()

        steps = {
            step.step: step
            for step in session.scalars(
                select(ProcessingStep).where(ProcessingStep.episode_id == episode.id)
            )
        }

        if redo is not None:
            if redo not in STEPS:
                raise UnknownStepError(
                    f"unknown step {redo}; expected one of: {', '.join(STEPS)}"
                )
            for name in STEPS[STEPS.index(redo) :]:
                step = steps[name]
                step.status = "pending"
                step.started_at = None
                step.finished_at = None
                step.error = None
            session.commit()

        outcomes: list[StepOutcome] = []
        for name in STEPS:
            step = steps[name]
            if step.status == "done":
                outcomes.append(StepOutcome(name, "skipped"))
                progress.step_finished(episode.video_id, name, "skipped", "", 0.0)
                continue

            step.status = "running"
            step.started_at = utcnow()
            step.finished_at = None
            step.error = None
            session.commit()
            if is_implemented(name):
                progress.step_started(episode.video_id, name)
            started = monotonic()

            try:
                run_step(name, episode, settings)
            except StepNotImplemented as exc:
                step.status = "pending"
                step.started_at = None
                session.commit()
                elapsed = monotonic() - started
                outcomes.append(StepOutcome(name, "not_implemented", str(exc)))
                progress.step_finished(
                    episode.video_id, name, "not_implemented", str(exc), elapsed
                )
                break
            except StopBatch as exc:
                step.status = "pending"
                step.started_at = None
                session.commit()
                elapsed = monotonic() - started
                outcomes.append(
                    StepOutcome(name, "stopped", str(exc), stop_batch=True)
                )
                progress.step_finished(
                    episode.video_id, name, "stopped", str(exc), elapsed
                )
                break
            except Exception as exc:  # noqa: BLE001 - recorded and surfaced to the CLI
                step.status = "failed"
                step.finished_at = utcnow()
                step.error = str(exc)[:2000]
                session.commit()
                elapsed = monotonic() - started
                outcomes.append(StepOutcome(name, "failed", str(exc)))
                progress.step_finished(
                    episode.video_id, name, "failed", str(exc), elapsed
                )
                break

            step.status = "done"
            step.finished_at = utcnow()
            session.commit()
            elapsed = monotonic() - started
            outcomes.append(StepOutcome(name, "done"))
            progress.step_finished(episode.video_id, name, "done", "", elapsed)

    return outcomes


def ingest_all(
    settings: Settings,
    *,
    redo: str | None = None,
    limit: int | None = None,
    progress: ProgressSink | None = None,
) -> list[tuple[str, list[StepOutcome]]]:
    """Run the pipeline for pending episodes, in playlist order.

    Without ``redo``, only episodes that have not finished the last implemented
    step are selected, so repeated runs advance through the catalog by
    themselves. With ``redo``, every episode is eligible.
    """
    progress = progress or ProgressSink()
    ensure_schema(settings)
    selected = _select_episodes(settings, redo=redo, limit=limit)

    results: list[tuple[str, list[StepOutcome]]] = []
    for index, (video_id, title) in enumerate(selected, start=1):
        progress.episode_started(video_id, title, index, len(selected))
        outcomes = ingest_episode(
            settings, video_id, redo=redo, progress=progress
        )
        progress.episode_finished(video_id, outcomes)
        results.append((video_id, outcomes))
        if any(outcome.stop_batch for outcome in outcomes):
            break
    return results


def count_pending(settings: Settings) -> int:
    """How many episodes still need the last implemented step."""
    target = target_step()
    ensure_schema(settings)
    with session_scope(settings) as session:
        episodes = session.scalars(select(Episode)).all()
        return sum(
            1 for episode in episodes if _step_status(episode, target) != "done"
        )


def _select_episodes(
    settings: Settings, *, redo: str | None, limit: int | None
) -> list[tuple[str, str]]:
    with session_scope(settings) as session:
        episodes = list(
            session.scalars(
                select(Episode).order_by(
                    Episode.playlist_position.is_(None),
                    Episode.playlist_position,
                    Episode.id,
                )
            )
        )
        if redo is None:
            target = target_step()
            episodes = [
                episode
                for episode in episodes
                if _step_status(episode, target) != "done"
            ]
        if limit is not None:
            episodes = episodes[:limit]
        return [(episode.video_id, episode.title) for episode in episodes]


def _step_status(episode: Episode, step: str) -> str:
    for row in episode.steps:
        if row.step == step:
            return row.status
    return "pending"
