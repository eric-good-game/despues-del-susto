# 0006 — Subtitles: automatic Spanish captions in `json3`

## Context

The anchor step needs the episode text with timestamps. The project does not publish subtitles, so
they are an internal artifact. YouTube already generates Spanish captions for the podcast, and
`yt-dlp` can download them without an API key.

## Decision

- Source: **automatic captions** (`--write-auto-subs`) in **`json3`**, because that is the only
  format the anchor step parses.
- Languages: `--sub-langs "es.*"`. If several Spanish variants arrive, one is kept by preference
  (`es`, `es-orig`, `es-419`, `es-mx`, `es-es`, then any other `es*`) and the rest are deleted.
- Location: `data/subs/<video_id>.<lang>.json3`, one file per episode.
- Missing subtitles are a **state**, not a failure: `subtitles_available = false`, the step
  finishes, and the audio step later uses its fallback window.
- A `yt-dlp` failure is a real failure: the step is marked `failed` and the run stops so it can be
  retried.

## Alternatives considered

- **Manual captions.** Better quality when they exist, but they are not consistently available and
  usually not in `json3`. Mixing both formats would complicate the parser for little gain.
- **YouTube Data API.** Official, but requires a key and consumes quota; `yt-dlp` already does the
  job from a residential connection.
- **Local transcription of the whole episode.** That is the audio step's job on a small window, not
  a substitute for subtitles.

## Consequences

- Automatic captions have recognition errors, especially with proper names. That is expected: the
  subtitles are one of two sources the extraction will contrast later.
- The pipeline depends on YouTube keeping the `json3` format available. If it disappears, only the
  subtitle step and its parser change.
- One file per episode keeps the artifact tree predictable and lets the anchor step run without
  touching the database.
