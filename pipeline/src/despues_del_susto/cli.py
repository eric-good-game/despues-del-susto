"""Command-line entry point for the local pipeline."""

import typer

from despues_del_susto import __version__

app = typer.Typer(
    name="dds",
    help="Local pipeline for the Despues del Susto catalog.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Local pipeline for the Despues del Susto catalog."""


@app.command()
def version() -> None:
    """Print the pipeline version."""
    typer.echo(__version__)
