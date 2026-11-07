"""Run the pipeline for one episode."""

from dataclasses import dataclass

from sqlalchemy import select

from despues_del_susto.config import Settings
from despues_del_susto.db import Episode, ProcessingStep, ensure_schema, session_scope
from despues_del_susto.db.models import utcnow
from despues_del_susto.steps import STEPS, run_step


class UnknownEpisodeError(RuntimeError):
    """The requested episode is not registered."""


@dataclass(frozen=True)
class StepOutcome:
    step: str
    status: str  # done | skipped | failed
    detail: str = ""


def ingest_episode(settings: Settings, video_id: str) -> list[StepOutcome]:
    """Run every step for one episode, skipping the ones already done.

    Steps run in order and stop at the first failure, so a retry resumes from
    the failed step instead of repeating finished work.
    """
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

        outcomes: list[StepOutcome] = []
        for name in STEPS:
            step = steps[name]
            if step.status == "done":
                outcomes.append(StepOutcome(name, "skipped"))
                continue

            step.status = "running"
            step.started_at = utcnow()
            step.finished_at = None
            step.error = None
            session.commit()

            try:
                run_step(name, episode, settings)
            except Exception as exc:  # noqa: BLE001 - recorded and surfaced to the CLI
                step.status = "failed"
                step.finished_at = utcnow()
                step.error = str(exc)[:2000]
                session.commit()
                outcomes.append(StepOutcome(name, "failed", str(exc)))
                break

            step.status = "done"
            step.finished_at = utcnow()
            session.commit()
            outcomes.append(StepOutcome(name, "done"))

    return outcomes
