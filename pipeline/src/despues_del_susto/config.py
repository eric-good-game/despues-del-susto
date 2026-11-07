"""Application settings, read from the environment and from ``.env``."""

from pathlib import Path

from pydantic import field_validator
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

    # Episode discovery
    yt_dlp_path: str = "yt-dlp"
    yt_dlp_timeout_s: int = 120
    sync_delay_s: float = 2.0
    sync_min_ratio: float = 0.5

    # Audio window
    audio_quality: str = "48K"
    audio_timeout_s: int = 600

    # Transcription
    transcribe_timeout_s: float = 300.0

    # Extraction
    extract_timeout_s: float = 180.0

    # Enrichment
    metadata_language: str = "es-MX"
    region: str = "MX"
    match_threshold: float = 0.85
    match_min_difference: float = 0.05
    max_candidates: int = 5
    igdb_delay_s: float = 0.26
    metadata_timeout_s: float = 30.0

    @property
    def db_path(self) -> Path:
        """Where the SQLite database lives."""
        return self.database_path or self.data_dir / "dds.db"

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for the local database."""
        return f"sqlite:///{self.db_path}"


class GroqSettings(BaseSettings):
    """Groq credentials, read without the ``DDS_`` prefix.

    ``GROQ_API_KEY`` and ``GROQ_MODEL`` are the names the previous prototype and
    the user's ``.env`` already use.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    groq_model: str = "whisper-large-v3"


class LlmSettings(BaseSettings):
    """Chat provider for recommendation extraction.

    The provider is selected with ``PROVIDER``. Groq uses ``GROQ_CHAT_MODEL`` for
    chat, because ``GROQ_MODEL`` belongs to transcription.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_models: str = ""
    groq_api_key: str = ""
    groq_chat_model: str = "llama-3.3-70b-versatile"
    groq_chat_fallback_models: str = ""
    opencode_api_key: str = ""
    opencode_model: str = ""
    opencode_fallback_models: str = ""
    opencode_base_url: str = "https://opencode.ai/inference/go/openai/v1"

    @field_validator("provider", mode="before")
    @classmethod
    def _clean_provider(cls, value: object) -> str:
        return str(value).split("#", 1)[0].strip().lower()


class MetadataSettings(BaseSettings):
    """TMDB and Twitch credentials, read without the ``DDS_`` prefix."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tmdb_token: str = ""
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
