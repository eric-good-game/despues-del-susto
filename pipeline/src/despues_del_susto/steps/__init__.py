"""Pipeline steps, in execution order.

Each phase replaces one stub with a real implementation. The dispatch lives
here so the orchestrator does not change when a step becomes real.
"""

from despues_del_susto.config import Settings
from despues_del_susto.db.models import Episode
from despues_del_susto.steps import anchor, audio, enrich, extract, subs, transcribe
from despues_del_susto.steps.errors import StepNotImplemented, StopBatch

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
    "transcribe": transcribe.run,
    "extract": extract.run,
    "enrich": enrich.run,
}

__all__ = [
    "STEPS",
    "StepNotImplemented",
    "StopBatch",
    "is_implemented",
    "run_step",
    "target_step",
]


def is_implemented(step: str) -> bool:
    """Whether the step has a real implementation."""
    return step in _RUNNERS


def run_step(step: str, episode: Episode, settings: Settings) -> None:
    """Execute one step for one episode."""
    runner = _RUNNERS.get(step)
    if runner is None:
        raise StepNotImplemented(step)
    runner(episode, settings)


def target_step() -> str:
    """The last step that has an implementation.

    Batch runs select episodes that have not finished this step, so the target
    advances by itself when a phase implements the next step.
    """
    for step in reversed(STEPS):
        if step in _RUNNERS:
            return step
    raise RuntimeError("no step has an implementation")
