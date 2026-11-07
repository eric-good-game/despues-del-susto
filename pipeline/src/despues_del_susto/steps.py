"""Pipeline steps, in execution order.

Phase 1 defines the order and runs every step as a stub. Each phase replaces one
stub with a real implementation without touching the orchestrator.
"""

import logging

from despues_del_susto.config import Settings
from despues_del_susto.db.models import Episode

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


def run_step(step: str, episode: Episode, settings: Settings) -> None:
    """Execute one step for one episode.

    This is the walking-skeleton implementation: it logs and returns. Real work
    arrives with the phase that owns each step.
    """
    logger.debug("step %s for %s: stub, nothing to do yet", step, episode.video_id)
