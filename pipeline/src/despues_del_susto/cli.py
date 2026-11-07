"""Command-line entry point for the local pipeline."""

from collections.abc import Sequence

import typer
from rich.console import Console
from rich.table import Table

from despues_del_susto import __version__
from despues_del_susto.config import Settings
from despues_del_susto.db import ensure_schema
from despues_del_susto.log import configure_logging
from despues_del_susto.progress import ProgressSink
from despues_del_susto.services.episodes import (
    DuplicateEpisodeError,
    add_episode,
    list_status,
)
from despues_del_susto.services.ingest import (
    StepOutcome,
    UnknownEpisodeError,
    UnknownStepError,
    count_pending,
    ingest_all,
    ingest_episode,
)
from despues_del_susto.services.sync import (
    DiscoveryNotConfigured,
    SyncError,
    SyncReport,
    sync_playlist,
)
from despues_del_susto.steps import STEPS, target_step

app = typer.Typer(
    name="dds",
    help="Local pipeline for the Despues del Susto catalog.",
    no_args_is_help=True,
    add_completion=False,
)
db_app = typer.Typer(help="Database commands.", no_args_is_help=True)
episode_app = typer.Typer(help="Episode commands.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(episode_app, name="episode")


class ConsoleProgress(ProgressSink):
    """Plain progress lines.

    Single-episode runs write them to stdout, because the steps are the result.
    Batches and sync write them to stderr, keeping stdout for the final report.
    """

    def __init__(self, *, err: bool, quiet: bool = False) -> None:
        self.err = err
        self.quiet = quiet
        self._indent = ""

    def episode_started(
        self, video_id: str, title: str, index: int, total: int
    ) -> None:
        self._indent = "  "
        self._write(f"[{index:2}/{total}] {video_id}  {title}")

    def step_started(self, video_id: str, step: str) -> None:
        self._write(f"{self._indent}{step}: running")

    def step_finished(
        self,
        video_id: str,
        step: str,
        status: str,
        detail: str,
        elapsed_s: float,
    ) -> None:
        self._write(f"{self._indent}{step}: {_describe(status, detail, elapsed_s)}")

    def episode_finished(
        self, video_id: str, outcomes: Sequence[StepOutcome]
    ) -> None:
        done = sum(1 for outcome in outcomes if outcome.status == "done")
        skipped = sum(1 for outcome in outcomes if outcome.status == "skipped")
        failed = next(
            (outcome for outcome in outcomes if outcome.status == "failed"), None
        )
        stopped = next(
            (
                outcome
                for outcome in outcomes
                if outcome.status in ("not_implemented", "stopped")
            ),
            None,
        )
        if failed is not None:
            suffix = f", failed at {failed.step}"
        elif stopped is not None:
            suffix = f", stopped at {stopped.step}"
        else:
            suffix = ""
        self._indent = ""
        if self.err and self.quiet:
            return
        typer.echo(f"{video_id}: done {done}, skipped {skipped}{suffix}", err=self.err)

    def metadata_started(self, video_id: str, index: int, total: int) -> None:
        self._write(f"metadata {index}/{total}  {video_id}")

    def metadata_failed(self, video_id: str, detail: str) -> None:
        self._write(f"metadata failed: {video_id} — {detail}")

    def _write(self, message: str) -> None:
        if not self.quiet:
            typer.echo(message, err=self.err)


def _describe(status: str, detail: str, elapsed_s: float) -> str:
    if status == "done":
        return f"done ({elapsed_s:.1f}s)"
    if status == "skipped":
        return "skipped"
    if status == "failed":
        return f"failed — {detail}"
    if status == "not_implemented":
        return "not implemented yet"
    if status == "stopped":
        return f"stopped — {detail}"
    return status


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Only print the final report."),
) -> None:
    """Local pipeline for the Despues del Susto catalog."""
    configure_logging(Settings().log_level, verbose=verbose)
    ctx.obj = {"quiet": quiet}


@app.command()
def version() -> None:
    """Print the pipeline version."""
    typer.echo(__version__)


@app.command()
def sync(
    ctx: typer.Context,
    playlist_url: str | None = typer.Option(
        None, "--playlist-url", help="YouTube playlist URL; overrides DDS_PLAYLIST_URL."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without writing anything."
    ),
    force: bool = typer.Option(
        False, "--force", help="Apply the listing even if it looks truncated."
    ),
) -> None:
    """Discover episodes in the playlist and refresh their metadata."""
    progress = ConsoleProgress(err=True, quiet=_quiet(ctx))
    try:
        report = sync_playlist(
            Settings(),
            playlist_url,
            dry_run=dry_run,
            force=force,
            progress=progress,
        )
    except (DiscoveryNotConfigured, SyncError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_sync_report(report)


@app.command()
def ingest(
    ctx: typer.Context,
    video_id: str | None = typer.Argument(None, help="YouTube video id."),
    all_episodes: bool = typer.Option(
        False, "--all", help="Process pending episodes in playlist order."
    ),
    redo: str | None = typer.Option(
        None, "--redo", help="Re-run this step and every step after it."
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Process at most N episodes (requires --all)."
    ),
) -> None:
    """Run the pipeline steps for one episode, or for a batch with --all."""
    if redo is not None and redo not in STEPS:
        typer.echo(f"unknown step {redo}; expected one of: {', '.join(STEPS)}", err=True)
        raise typer.Exit(code=1)
    if video_id is None and not all_episodes:
        typer.echo("pass a video_id or use --all", err=True)
        raise typer.Exit(code=1)
    if video_id is not None and all_episodes:
        typer.echo("pass a video_id or --all, not both", err=True)
        raise typer.Exit(code=1)
    if limit is not None and not all_episodes:
        typer.echo("--limit requires --all", err=True)
        raise typer.Exit(code=1)
    if limit is not None and limit < 1:
        typer.echo("--limit must be at least 1", err=True)
        raise typer.Exit(code=1)

    settings = Settings()
    quiet = _quiet(ctx)
    if video_id is not None:
        progress = ConsoleProgress(err=False, quiet=quiet)
        try:
            outcomes = ingest_episode(
                settings, video_id, redo=redo, progress=progress
            )
        except (UnknownEpisodeError, UnknownStepError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        progress.episode_finished(video_id, outcomes)
        if any(outcome.status == "failed" for outcome in outcomes):
            raise typer.Exit(code=1)
        return

    progress = ConsoleProgress(err=True, quiet=quiet)
    results = ingest_all(settings, redo=redo, limit=limit, progress=progress)
    failed_episodes = sum(
        1
        for _, outcomes in results
        if any(outcome.status == "failed" for outcome in outcomes)
    )
    stopped = any(
        outcome.stop_batch for _, outcomes in results for outcome in outcomes
    )
    remaining = count_pending(settings)
    typer.echo(
        f"Batch: {len(results)} processed, {failed_episodes} failed, "
        f"{remaining} pending for {target_step()}."
    )
    if stopped:
        typer.echo("Batch stopped early; run the same command again later.", err=True)
    if failed_episodes or stopped:
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show every registered episode and how far its processing got."""
    rows = list_status(Settings())
    if not rows:
        typer.echo('No episodes yet. Add one with: dds episode add <video_id> --title "..."')
        return

    table = Table(title="Episodes")
    table.add_column("video_id")
    table.add_column("title")
    table.add_column("availability")
    table.add_column("steps")
    table.add_column("state")
    table.add_column("error")
    for row in rows:
        title = row.title if len(row.title) <= 50 else row.title[:47] + "..."
        table.add_row(
            row.video_id,
            title,
            row.availability,
            f"{row.steps_done}/{row.steps_total}",
            row.state,
            row.error or "",
        )
    Console().print(table)


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Create or migrate the local database."""
    settings = Settings()
    ensure_schema(settings)
    typer.echo(f"Database ready: {settings.db_path}")


@episode_app.command("add")
def episode_add(
    video_id: str = typer.Argument(..., help="YouTube video id."),
    title: str = typer.Option(..., "--title", "-t", help="Episode title."),
) -> None:
    """Register one episode manually, without touching the network."""
    try:
        episode = add_episode(Settings(), video_id, title)
    except (DuplicateEpisodeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Added episode {episode.video_id}: {episode.title}")


def _quiet(ctx: typer.Context) -> bool:
    if not ctx.obj:
        return False
    return bool(ctx.obj.get("quiet", False))


def _print_sync_report(report: SyncReport) -> None:
    if report.dry_run:
        typer.echo("Dry run: nothing was written.")
    typer.echo(f"added: {len(report.added)}")
    for video_id in report.added:
        typer.echo(f"  + {video_id}")
    typer.echo(f"updated: {len(report.updated)}")
    for video_id in report.updated:
        typer.echo(f"  ~ {video_id}")
    typer.echo(f"unavailable: {len(report.unavailable)}")
    for video_id in report.unavailable:
        typer.echo(f"  - {video_id}")
    typer.echo(f"reactivated: {len(report.reactivated)}")
    for video_id in report.reactivated:
        typer.echo(f"  + {video_id}")
    typer.echo(f"unchanged: {report.unchanged}")
    if report.dry_run and report.metadata_pending:
        typer.echo(f"metadata pending: {len(report.metadata_pending)}")
    if report.metadata_fetched:
        typer.echo(f"metadata fetched: {len(report.metadata_fetched)}")
    if report.metadata_failed:
        typer.echo(f"metadata failed: {len(report.metadata_failed)}", err=True)
        for video_id, error in report.metadata_failed.items():
            typer.echo(f"  ! {video_id}: {error}", err=True)
