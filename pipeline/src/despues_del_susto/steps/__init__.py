"""Pipeline steps, in execution order.

Each phase replaces one stub with a real implementation. The dispatch lives
here so the orchestrator does not change when a step becomes real.
"""

import logging

from despues_del_susto.config import Settings
from despues_del_susto.db.models import Episode
from despues_del_susto.steps import anchor, subs

logger = logging.getLogger(__name__)

STEPS: tuple[str, ...] = (
    "subs",
    "anchor",
    "audio",
    "transcribe",
    "extract",
    "enrich",
    "publish",
)

_RUNNERS = {
    "subs": subs.run,
    "anchor": anchor.run,
}


def run_step(step: str, episode: Episode, settings: Settings) -> None:
    """Execute one step for one episode."""
    runner = _RUNNERS.get(step)
    if runner is None:
        logger.debug("step %s for %s: stub, nothing to do yet", step, episode.video_id)
        return
    runner(episode, settings)
