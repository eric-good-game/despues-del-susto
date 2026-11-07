# Después del Susto

A fan-made catalog of the videogames, movies and other works recommended at the end of each
episode of the *Tengo Miedo* podcast.

> Unofficial fan project. Not affiliated with the podcast, Franco Escamilla or his channel.

## Status

Version 1 runs entirely on the author's machine, in Python. There is no web server yet; publishing
is a later phase. The project is at **phase 2, episode discovery**: the playlist is read with
`yt-dlp`, episodes are upserted by `video_id`, and metadata is refreshed only where it is missing.
See [`WORKFLOW.md`](WORKFLOW.md) and [`docs/pipeline.md`](docs/pipeline.md).

## Why local first

Downloading audio has to happen from a residential connection: YouTube blocks or challenges
datacenter IPs. The first version therefore keeps every step on the author's machine and leaves
the server for later. Nothing is designed in a way that would prevent moving to a server; it is
simply not a concern yet.

## Requirements

- Python 3.12
- `ffmpeg` — audio handling
- `yt-dlp` — episode subtitles and audio

## Setup

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e "pipeline[dev]"
cp .env.example .env   # fill in only the keys the current phase needs
```

## Usage

```sh
dds --help

dds db upgrade                                   # explicit; other commands migrate too
dds episode add <video_id> --title "Episode title"
dds ingest <video_id>                            # runs the seven steps, resuming where needed
dds status                                       # one row per episode

dds sync --dry-run                               # preview what the playlist would change
dds sync                                         # apply it; uses DDS_PLAYLIST_URL
```

## Layout

| Path | What lives there |
|---|---|
| `pipeline/` | Python package and CLI (`dds`): ingestion, transcription, extraction, enrichment |
| `pipeline/src/despues_del_susto/` | Source code |
| `pipeline/tests/` | Tests |
| `data/` | Local artifacts and the SQLite database. Not versioned. |
| `docs/` | Glossary, data model, pipeline contract and decision records, written as each phase needs them |
| `prev/` | Earlier prototype. Reference only. Not versioned. |

## Conventions

- Documentation, code, database names and data values are in English. Site copy shown to visitors
  is in Spanish, and lives in the presentation layer.
- Business rules are `BR-xx`; use cases are `UC-xx`.
- Commit format, branching and definition of done: [`WORKFLOW.md`](WORKFLOW.md).
