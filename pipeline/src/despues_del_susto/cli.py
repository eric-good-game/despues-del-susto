"""Command-line entry point for the local pipeline."""

import typer
from rich.console import Console
from rich.table import Table

from despues_del_susto import __version__
from despues_del_susto.config import Settings
from despues_del_susto.db import ensure_schema
from despues_del_susto.log import configure_logging
from despues_del_susto.services.episodes import (
    DuplicateEpisodeError,
    add_episode,
    list_status,
)
from despues_del_susto.services.ingest import UnknownEpisodeError, ingest_episode
from despues_del_susto.services.sync import DiscoveryNotConfigured, sync_playlist

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


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Local pipeline for the Despues del Susto catalog."""
    configure_logging(Settings().log_level, verbose=verbose)


@app.command()
def version() -> None:
    """Print the pipeline version."""
    typer.echo(__version__)


@app.command()
def sync(
    playlist_url: str | None = typer.Option(
        None, "--playlist-url", help="YouTube playlist URL; overrides DDS_PLAYLIST_URL."
    ),
) -> None:
    """Discover episodes in the podcast playlist (implemented in phase 2)."""
    try:
        episodes = sync_playlist(Settings(), playlist_url)
    except DiscoveryNotConfigured as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except NotImplementedError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"{len(episodes)} episodes discovered")


@app.command()
def ingest(video_id: str = typer.Argument(..., help="YouTube video id.")) -> None:
    """Run every pipeline step for one episode, skipping finished steps."""
    try:
        outcomes = ingest_episode(Settings(), video_id)
    except UnknownEpisodeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    failed = False
    for outcome in outcomes:
        if outcome.status == "failed":
            typer.echo(f"{outcome.step}: failed — {outcome.detail}", err=True)
            failed = True
        else:
            typer.echo(f"{outcome.step}: {outcome.status}")
    if failed:
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
