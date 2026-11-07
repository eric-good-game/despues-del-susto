"""Pipeline steps, in execution order.

Each phase replaces one stub with a real implementation. The dispatch lives
here so the orchestrator does not change when a step becomes real.
"""

from despues_del_susto.config import Settings
from despues_del_susto.db.models import Episode
from despues_del_susto.steps import anchor, audio, subs

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
    "audio": audio.run,
}


class StepNotImplemented(RuntimeError):
    """The step exists in the pipeline but has no implementation yet."""

    def __init__(self, step: str) -> None:
        super().__init__(f"step {step} is not implemented yet")
        self.step = step


def run_step(step: str, episode: Episode, settings: Settings) -> None:
    """Execute one step for one episode."""
    runner = _RUNNERS.get(step)
    if runner is None:
        raise StepNotImplemented(step)
    runner(episode, settings)
