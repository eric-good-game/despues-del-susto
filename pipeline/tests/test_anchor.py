import json
from pathlib import Path

from despues_del_susto.steps.anchor import SubtitleEvent, detect, load_events


def _events(*items: tuple[int, str]) -> list[SubtitleEvent]:
    return [SubtitleEvent(start_s=start, text=text) for start, text in items]


def test_detect_ok_and_takes_the_earliest_kind() -> None:
    events = _events(
        (2990, "tenemos recomendaciones"),
        (3000, "que videojuego recomiendas"),
        (3100, "recomendacion de pelicula"),
        (3590, "gracias"),
    )

    result = detect(events, 3610)

    assert result.state == "ok"
    assert result.anchor_s == 2990
    assert result.anchor_kinds == ("intro", "juego", "peli")
    assert result.tail_s == 620
    assert result.evidence


def test_detect_partial_when_a_kind_is_missing() -> None:
    events = _events(
        (3000, "que videojuego recomiendas"),
        (3590, "gracias"),
    )

    result = detect(events, 3610)

    assert result.state == "parcial"
    assert result.anchor_kinds == ("juego",)


def test_detect_ignores_the_first_half() -> None:
    events = _events(
        (1000, "que videojuego recomiendas"),
        (3590, "gracias"),
    )

    assert detect(events, 3610).state == "sin_ancla"


def test_detect_ignores_an_anchor_too_far_from_the_end() -> None:
    events = _events(
        (2000, "que videojuego recomiendas"),
        (3590, "gracias"),
    )

    assert detect(events, 3610).state == "sin_ancla"


def test_detect_without_events_or_duration() -> None:
    assert detect([], 100).state == "sin_ancla"
    assert detect([SubtitleEvent(1, "hola")], 0).state == "sin_ancla"


def test_load_events_drops_rolling_caption_prefixes(tmp_path: Path) -> None:
    payload = {
        "events": [
            {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": "hola"}]},
            {"tStartMs": 1100, "dDurationMs": 1000, "segs": [{"utf8": "hola a"}]},
            {"tStartMs": 1200, "dDurationMs": 1000, "segs": [{"utf8": "hola a todos"}]},
            {"tStartMs": 2000, "dDurationMs": 1000, "segs": [{"utf8": "adios"}]},
        ]
    }
    path = tmp_path / "abc.es.json3"
    path.write_text(json.dumps(payload), encoding="utf-8")

    events, duration = load_events(path)

    assert [event.text for event in events] == ["hola a todos", "adios"]
    assert duration == 3.0
