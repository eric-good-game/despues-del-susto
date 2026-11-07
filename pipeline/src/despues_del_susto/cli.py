"""Command-line entry point for the local pipeline."""

from collections.abc import Sequence

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from despues_del_susto import __version__
from despues_del_susto.config import Settings
from despues_del_susto.db import ensure_schema
from despues_del_susto.log import configure_logging
from despues_del_susto.progress import ProgressSink
from despues_del_susto.services import review as review_service
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
from despues_del_susto.services.matching import ScoredCandidate
from despues_del_susto.services.review import CandidateView, ReviewCase, ReviewError
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
review_app = typer.Typer(
    help="Review pending recommendation matches.",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(db_app, name="db")
app.add_typer(episode_app, name="episode")
app.add_typer(review_app, name="review")


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


@review_app.callback()
def review_main(
    ctx: typer.Context,
    episode: str | None = typer.Option(
        None, "--episode", help="Only this YouTube video id."
    ),
    all_cases: bool = typer.Option(
        False, "--all", help="Include confirmed matches."
    ),
) -> None:
    """Review pending matches interactively."""
    if ctx.invoked_subcommand is not None:
        return
    _review_interactive(episode, all_cases)


@review_app.command("status")
def review_status() -> None:
    """Show how many recommendations are pending and resolved."""
    summary = review_service.status_summary(Settings())
    counts = summary["counts"]
    table = Table(title="Review status")
    table.add_column("State")
    table.add_column("Count", justify="right")
    for state in (
        "needs_review",
        "no_match",
        "manual_pending",
        "confirmed",
        "manual_resolved",
        "discarded",
        "extracted",
    ):
        table.add_row(state, str(counts.get(state, 0)))
    Console().print(table)
    typer.echo(
        f"Recommendations: {summary['total']} · Works: {summary['works']} · "
        f"Episodes with pending: {summary['pending_episodes']}"
    )


def _review_interactive(episode: str | None, all_cases: bool) -> None:
    console = Console()
    settings = Settings()
    cases = review_service.list_cases(
        settings, episode=episode, include_confirmed=all_cases
    )
    if not cases:
        console.print(
            "No cases pending." if not all_cases else "No cases to review."
        )
        return

    for index, case in enumerate(cases, start=1):
        console.rule(
            f"[{index}/{len(cases)}] {case.episode_video_id} · {case.type} · {case.state}"
        )
        console.print(f"Episode: {case.episode_title}")
        probable = case.probable_title or "—"
        console.print(f'Mentioned: "{case.mentioned_title}"   Probable: "{probable}"')
        mention = case.mention_s if case.mention_s is not None else "—"
        console.print(f"Confidence: {case.confidence}   Mention second: {mention}")
        if case.match_note:
            console.print(
                f"Current match: {case.match_note} (score {case.match_score or 0:.2f})"
            )

        if case.candidates:
            console.print(_candidate_table(case.candidates))
        else:
            console.print("[yellow]No candidates stored.[/yellow]")

        choices = [str(number) for number in range(1, len(case.candidates) + 1)]
        choices += ["s", "m", "d", "k", "q"]
        choice = Prompt.ask("Action", choices=choices, default="k")

        try:
            if choice == "q":
                break
            if choice == "k":
                continue
            if choice == "d":
                review_service.discard(settings, case.recommendation_id)
                console.print("[green]Discarded.[/green]")
                continue
            if choice == "m":
                _review_manual(console, settings, case)
                continue
            if choice == "s":
                _review_search(console, settings, case)
                continue

            candidate = case.candidates[int(choice) - 1]
            work = review_service.resolve_candidate(
                settings,
                case.recommendation_id,
                source=candidate.source,
                type=candidate.type,
                external_id=candidate.external_id,
                title=candidate.title,
                year=candidate.year,
                image_url=candidate.image_url,
                score=candidate.score,
            )
            console.print(
                f"[green]Linked to work #{work.id}: {work.official_title} "
                f"({work.year or '—'})[/green]"
            )
        except ReviewError as exc:
            console.print(f"[red]{exc}[/red]")

    console.print("Review finished.")


def _review_manual(console: Console, settings: Settings, case: ReviewCase) -> None:
    title = Prompt.ask("Title", default=case.probable_title or case.mentioned_title)
    year_text = Prompt.ask("Year (optional)", default="")
    description = Prompt.ask("Description (optional)", default="")
    image_url = Prompt.ask("Image URL (optional)", default="")
    year = int(year_text) if year_text.strip().isdigit() else None
    work = review_service.resolve_manual(
        settings,
        case.recommendation_id,
        type=case.type,
        title=title,
        year=year,
        description=description or None,
        image_url=image_url or None,
    )
    console.print(f"[green]Manual work #{work.id}: {work.official_title}[/green]")


def _review_search(console: Console, settings: Settings, case: ReviewCase) -> None:
    query = Prompt.ask(
        "New search", default=case.probable_title or case.mentioned_title
    )
    try:
        scored = review_service.search_alternatives(
            settings, case.recommendation_id, query
        )
    except ReviewError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    if not scored:
        console.print("[yellow]No results.[/yellow]")
        return

    console.print(_scored_table(scored))
    choices = [str(number) for number in range(1, len(scored) + 1)] + ["b"]
    choice = Prompt.ask("Choose", choices=choices, default="b")
    if choice == "b":
        return

    item = scored[int(choice) - 1]
    try:
        work = review_service.resolve_candidate(
            settings,
            case.recommendation_id,
            source=item.candidate.source,
            type=item.candidate.type,
            external_id=item.candidate.external_id,
            title=item.candidate.title,
            year=item.candidate.year,
            image_url=item.candidate.image_url,
            score=item.score,
            scored=scored,
        )
    except ReviewError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    console.print(
        f"[green]Linked to work #{work.id}: {work.official_title} "
        f"({work.year or '—'})[/green]"
    )


def _candidate_table(candidates: list[CandidateView]) -> Table:
    table = Table(title="Candidates")
    table.add_column("#", justify="right")
    table.add_column("Source")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Year")
    table.add_column("Score", justify="right")
    table.add_column("Image")
    for position, candidate in enumerate(candidates, start=1):
        table.add_row(
            str(position),
            candidate.source,
            candidate.type,
            candidate.title,
            str(candidate.year or "—"),
            f"{candidate.score:.2f}",
            candidate.image_url or "",
        )
    return table


def _scored_table(scored: list[ScoredCandidate]) -> Table:
    table = Table(title="Search results")
    table.add_column("#", justify="right")
    table.add_column("Source")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Year")
    table.add_column("Score", justify="right")
    table.add_column("Image")
    for position, item in enumerate(scored, start=1):
        candidate = item.candidate
        table.add_row(
            str(position),
            candidate.source,
            candidate.type,
            candidate.title,
            str(candidate.year or "—"),
            f"{item.score:.2f}",
            candidate.image_url or "",
        )
    return table


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
