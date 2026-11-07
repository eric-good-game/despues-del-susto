from pathlib import Path

from despues_del_susto.config import Settings
from despues_del_susto.steps.subtitles import download_subtitles, find_subtitle_file


def test_download_prefers_es_and_deletes_the_other_languages(
    tmp_path: Path, monkeypatch
) -> None:
    settings = Settings(data_dir=tmp_path)

    def fake_run(settings, arguments):
        directory = tmp_path / "subs"
        for language in ("es-419", "es", "es-orig"):
            (directory / f"abc.{language}.json3").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("despues_del_susto.steps.subtitles.run_command", fake_run)

    download = download_subtitles(settings, "abc")

    assert download.available
    assert download.language == "es"
    assert download.path is not None
    assert download.path.name == "abc.es.json3"
    assert [path.name for path in (tmp_path / "subs").iterdir()] == ["abc.es.json3"]


def test_download_without_files_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(
        "despues_del_susto.steps.subtitles.run_command",
        lambda settings, arguments: None,
    )

    download = download_subtitles(settings, "abc")

    assert not download.available
    assert download.language is None


def test_find_subtitle_file_without_files(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)

    assert find_subtitle_file(settings, "abc") is None
