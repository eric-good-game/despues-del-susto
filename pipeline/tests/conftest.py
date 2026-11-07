from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from despues_del_susto.cli import app

runner = CliRunner()

Invoke = Callable[..., Any]


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    data_dir = tmp_path / "data"
    return {
        "DDS_DATA_DIR": str(data_dir),
        "DDS_DATABASE_PATH": str(data_dir / "test.db"),
        "DDS_LOG_LEVEL": "WARNING",
        "DDS_PLAYLIST_URL": "",
        "DDS_SYNC_DELAY_S": "0",
    }


@pytest.fixture
def invoke(env: dict[str, str]) -> Invoke:
    def _invoke(*args: str) -> Any:
        return runner.invoke(app, list(args), env=env)

    return _invoke


@pytest.fixture
def db_path(env: dict[str, str]) -> Path:
    return Path(env["DDS_DATABASE_PATH"])
