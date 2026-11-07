from types import SimpleNamespace

import pytest

from despues_del_susto.config import Settings
from despues_del_susto.db import Episode, ensure_schema, session_scope
from despues_del_susto.steps import StopBatch
from despues_del_susto.steps import transcribe as transcribe_module
from despues_del_susto.steps.transcribe import (
    Segment,
    TranscriptionError,
    transcribe_audio,
)


class FakeError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def _fake_client(create) -> object:
    return SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )


def _settings() -> Settings:
    return Settings()


def test_transcribe_retries_transient_errors(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    calls = {"count": 0}
    response = SimpleNamespace(segments=[{"start": 1.5, "text": " hola "}])

    def create(**kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise FakeError(503)
        return response

    monkeypatch.setattr(transcribe_module, "OpenAI", lambda **kwargs: _fake_client(create))
    monkeypatch.setattr(transcribe_module.time, "sleep", lambda seconds: None)
    audio = tmp_path / "abc.mp3"
    audio.write_bytes(b"fake")

    result = transcribe_audio(_settings(), audio)

    assert result.segments == [Segment(1.5, "hola")]
    assert result.service == "groq"
    assert result.model == "test-model"
    assert calls["count"] == 3


def test_transcribe_stops_the_batch_after_a_rate_limit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    calls = {"count": 0}

    def create(**kwargs):
        calls["count"] += 1
        raise FakeError(429)

    monkeypatch.setattr(transcribe_module, "OpenAI", lambda **kwargs: _fake_client(create))
    monkeypatch.setattr(transcribe_module.time, "sleep", lambda seconds: None)
    audio = tmp_path / "abc.mp3"
    audio.write_bytes(b"fake")

    with pytest.raises(StopBatch, match="quota"):
        transcribe_audio(_settings(), audio)

    assert calls["count"] == 5


def test_transcribe_does_not_retry_a_permanent_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    calls = {"count": 0}

    def create(**kwargs):
        calls["count"] += 1
        raise FakeError(401)

    monkeypatch.setattr(transcribe_module, "OpenAI", lambda **kwargs: _fake_client(create))
    audio = tmp_path / "abc.mp3"
    audio.write_bytes(b"fake")

    with pytest.raises(TranscriptionError, match="transcription failed"):
        transcribe_audio(_settings(), audio)

    assert calls["count"] == 1


def test_transcribe_requires_the_api_key(monkeypatch, tmp_path) -> None:
    class NoKey:
        groq_api_key = ""
        groq_model = "test-model"

    monkeypatch.setattr(transcribe_module, "GroqSettings", lambda: NoKey())
    audio = tmp_path / "abc.mp3"
    audio.write_bytes(b"fake")

    with pytest.raises(TranscriptionError, match="GROQ_API_KEY"):
        transcribe_audio(_settings(), audio)


def test_segments_fall_back_to_the_text_field() -> None:
    response = SimpleNamespace(segments=[], text=" hola ")

    segments = transcribe_module._segments_from(response)

    assert segments == [Segment(0.0, "hola")]


def test_run_rejects_missing_audio(tmp_path) -> None:
    episode = SimpleNamespace(id=1, video_id="abc")

    with pytest.raises(TranscriptionError, match="audio window not found"):
        transcribe_module.run(episode, Settings(data_dir=tmp_path))


def test_run_rejects_episodes_without_a_window(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    ensure_schema(settings)
    with session_scope(settings) as session:
        episode = Episode(video_id="abc", title="Episode")
        session.add(episode)
        session.commit()
        episode_id = episode.id

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "abc.mp3").write_bytes(b"fake")

    with pytest.raises(TranscriptionError, match="audio step"):
        transcribe_module.run(
            SimpleNamespace(id=episode_id, video_id="abc"), settings
        )
