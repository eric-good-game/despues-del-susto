"""Application settings, read from the environment and from ``.env``."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the local pipeline.

    Every value can be overridden with an environment variable prefixed with
    ``DDS_`` or with a line in ``.env``. Relative paths are resolved against the
    current working directory, which is expected to be the repository root.
    """

    model_config = SettingsConfigDict(
        env_prefix="DDS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    database_path: Path | None = None
    playlist_url: str = ""
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        """Where the SQLite database lives."""
        return self.database_path or self.data_dir / "dds.db"

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for the local database."""
        return f"sqlite:///{self.db_path}"
