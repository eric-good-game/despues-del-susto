from typer.testing import CliRunner

from despues_del_susto import __version__
from despues_del_susto.cli import app

runner = CliRunner()


def test_version_command_prints_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_running_without_arguments_shows_help() -> None:
    result = runner.invoke(app, [])

    assert "Usage" in result.stdout
