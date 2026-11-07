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


class StopBatch(RuntimeError):
    """The step cannot continue the current batch.

    Used for conditions that are not a permanent failure, such as an exhausted
    API quota: the step stays pending and the batch stops instead of failing the
    remaining episodes one by one.
    """


def target_step() -> str:
    """The last step that has an implementation.

    Batch runs select episodes that have not finished this step, so the target
    advances by itself when a phase implements the next step.
    """
    for step in reversed(STEPS):
        if step in _RUNNERS:
            return step
    raise RuntimeError("no step has an implementation")


def run_step(step: str, episode: Episode, settings: Settings) -> None:
    """Execute one step for one episode."""
    runner = _RUNNERS.get(step)
    if runner is None:
        raise StepNotImplemented(step)
    runner(episode, settings)
