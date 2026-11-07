"""Exceptions shared by the pipeline steps."""


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
