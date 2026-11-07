"""Progress events for long-running commands.

Services only emit events; rendering belongs to the CLI. The base class is a
no-op so callers can pass it unconditionally.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from despues_del_susto.services.ingest import StepOutcome


class ProgressSink:
    """No-op progress sink. The CLI replaces it with a renderer."""

    def episode_started(
        self, video_id: str, title: str, index: int, total: int
    ) -> None:
        pass

    def step_started(self, video_id: str, step: str) -> None:
        pass

    def step_finished(
        self,
        video_id: str,
        step: str,
        status: str,
        detail: str,
        elapsed_s: float,
    ) -> None:
        pass

    def episode_finished(
        self, video_id: str, outcomes: Sequence[StepOutcome]
    ) -> None:
        pass

    def metadata_started(self, video_id: str, index: int, total: int) -> None:
        pass

    def metadata_failed(self, video_id: str, detail: str) -> None:
        pass
