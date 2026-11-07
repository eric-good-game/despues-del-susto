# Pipeline

The contract between the commands and the steps. It describes order, inputs and outputs, not the
internal logic of any step: that belongs to the phase that implements it.

## Order

```
sync  →  subs  →  anchor  →  audio  →  transcribe  →  extract  →  enrich  →  publish
```

`sync` is set-level: it discovers episodes and updates the catalog. Everything after it is
per-episode and runs under `dds ingest <video_id>`.

## 0. Sync (set-level)

| | |
|---|---|
| Purpose | Keep the `episodes` table in step with the playlist. |
| Input | Playlist URL (`DDS_PLAYLIST_URL` or `--playlist-url`). |
| Output | Episodes inserted or updated, keyed by `video_id`. |
| Idempotency key | `video_id`. |
| Phase 1 | Stub: validates configuration, then exits with "implemented in phase 2". |

## Per-episode steps

| Step | Purpose | Input | Output | Phase 1 |
|---|---|---|---|---|
| `subs` | Get the automatic subtitles. | `video_id` | `data/subs/<video_id>.<lang>.json3` | Stub |
| `anchor` | Find the recommendations section. | Subtitles | Anchor second, kind and state, stored in the database | Stub |
| `audio` | Download the audio window. | `video_id` and window start | `data/audio/<video_id>.mp3` and the window start in the database | Stub |
| `transcribe` | Turn the audio window into text with seconds. | Audio and window start | `data/transcripts/<video_id>.json` | Stub |
| `extract` | Pull recommendations out of the transcript. | Transcript | `data/extractions/<video_id>.json` | Stub |
| `enrich` | Match each work and fetch its details. | Extractions | `data/enriched/<video_id>.json` | Stub |
| `publish` | Produce the data the site will read. | Resolved episode | Publication artifact | Stub |

## Orchestration

- **Resumable.** A run skips every step whose state is `done`. The first step that is not `done`
  runs, and the rest follow in order.
- **Fail fast.** A failing step is marked `failed` with its message, and the run stops. The next
  run resumes at that step; finished steps are not repeated.
- **One state per step.** Starting a step sets `running`; finishing sets `done` or `failed`.
- **No hidden network calls.** Commands only do the work of their own step. `ingest` never syncs,
  and `sync` never ingests.
- **No parallel runs.** One episode is processed by one run at a time; SQLite and the step states
  make a second concurrent run unnecessary.

## Artifacts

Bulky intermediate output lives in `data/`, not in the database. See
[`decisions/0003-artifact-layout.md`](decisions/0003-artifact-layout.md).

```
data/
  dds.db
  subs/<video_id>.<lang>.json3
  audio/<video_id>.mp3
  transcripts/<video_id>.json
  extractions/<video_id>.json
  enriched/<video_id>.json
```

The database is the source of truth for state. An artifact may be regenerated; a step's recorded
state is what decides whether it runs again.

## Commands

| Command | Contract |
|---|---|
| `dds sync` | Set-level discovery. |
| `dds episode add <video_id> --title ...` | Manual registration, no network. |
| `dds ingest <video_id>` | Runs the seven steps, resuming where needed. |
| `dds status` | Reads the database and prints one row per episode. |
| `dds db upgrade` | Applies migrations. Every other command does this implicitly. |
