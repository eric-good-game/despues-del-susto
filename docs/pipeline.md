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
| Purpose | Keep the `episodes` table in step with the playlist and refresh metadata. |
| Input | Playlist URL (`DDS_PLAYLIST_URL` or `--playlist-url`). |
| Output | Episodes inserted, updated, marked unavailable or reactivated. |
| Idempotency key | `video_id`. Running it twice on the same playlist changes nothing. |
| Network | `yt-dlp --flat-playlist` for the listing, plus one full extraction per episode that still needs metadata. |

### 0.1 Listing

`yt-dlp --flat-playlist --dump-single-json <url>` returns the entries in playlist order.
The sync reads `id` and `title` and keeps the array position as `playlist_position`. Duplicate
ids are ignored after the first one; entries without an id are skipped.

### 0.2 Upsert

For each entry:

- **Not in the database** → insert with `availability = available`, `first_seen_at`,
  `last_seen_at`, and a metadata fetch pending.
- **Already there** → update `title` and `playlist_position` when they differ, set
  `last_seen_at`, and reactivate it if it was `unavailable`.
- **Same data** → counted as unchanged; nothing is written.

Episodes that exist in the database but not in the listing are marked `unavailable`. They are never
deleted. If they reappear in a later sync, they become `available` again.

### 0.3 Metadata

The flat listing has no date, duration or thumbnail. Those come from one full extraction per
episode whose `metadata_fetched_at` is empty: new episodes, episodes registered by hand, and
episodes whose last attempt failed.

- The title is **not** taken from the full extraction. The listing owns the title; two writers
  would make consecutive syncs overwrite each other.
- A failure records `metadata_error`, leaves `metadata_fetched_at` empty and does not stop the
  sync. The next sync retries it.
- Calls are spaced by `DDS_SYNC_DELAY_S` seconds.

### 0.4 Safety

The listing is refused, and nothing is written, when:

- `yt-dlp` fails or returns invalid JSON.
- The listing has zero entries.
- Fewer than `DDS_SYNC_MIN_RATIO` (default `0.5`) of the known available episodes appear, unless
  `--force` is passed.

The last rule stops a truncated response from marking most of the catalog unavailable. `--force`
is the explicit statement that the playlist really shrank.

### 0.5 Report and dry run

`dds sync` prints what changed: added, updated, unavailable, reactivated, unchanged, metadata
fetched and metadata failed, with the episode ids.

`--dry-run` runs the same comparison and prints the same report without writing anything and
without fetching metadata.

## Per-episode steps

| Step | Purpose | Input | Output | Status |
|---|---|---|---|---|
| `subs` | Get the automatic subtitles. | `video_id` | `data/subs/<video_id>.<lang>.json3` | Real |
| `anchor` | Find the recommendations section. | Subtitles | Anchor second, kinds, state and evidence in `episode_processing` | Real |
| `audio` | Download the audio window. | `video_id` and window start | `data/audio/<video_id>.mp3` and the window start in the database | Stub |
| `transcribe` | Turn the audio window into text with seconds. | Audio and window start | `data/transcripts/<video_id>.json` | Stub |
| `extract` | Pull recommendations out of the transcript. | Transcript | `data/extractions/<video_id>.json` | Stub |
| `enrich` | Match each work and fetch its details. | Extractions | `data/enriched/<video_id>.json` | Stub |
| `publish` | Produce the data the site will read. | Resolved episode | Publication artifact | Stub |

### Subtitles

`yt-dlp --skip-download --write-auto-subs --sub-format json3 --sub-langs "es.*"` downloads the
automatic Spanish captions into `data/subs/`. Only automatic captions are used, and only in
`json3`, because that is the format the anchor step parses.

- **One language per episode.** If several Spanish variants arrive, the preferred one wins
  (`es`, `es-orig`, `es-419`, `es-mx`, `es-es`, then any other `es*`), and the rest are deleted.
- **No subtitles is a state, not a failure.** The step records `subtitles_available = false` and
  finishes. The audio step will use its fallback window.
- **A yt-dlp failure is a failure.** The step is marked `failed` and the run stops, so the
  episode can be retried.

### Anchor

The anchor step reads the preferred subtitle file and looks for the sentence that opens the
recommendations section.

- It drops the repeated lines that YouTube's rolling captions produce before matching. Without
  that, the same sentence appears several times with growing prefixes.
- Text is normalized (lowercase, no accents) before matching. The patterns are in
  `steps/anchor.py`; the rules and thresholds are in [`rules.md`](rules.md).
- It stores `anchor_s`, `anchor_kinds`, `anchor_state`, `tail_s` and `anchor_evidence`. The
  evidence is internal: it exists to review a doubtful detection, never to publish.
- If there is no subtitle file, the result is `sin_ancla` and the step still succeeds.

## Orchestration

- **Resumable.** A run skips every step whose state is `done`. The first step that is not `done`
  runs, and the rest follow in order.
- **Fail fast.** A failing step is marked `failed` with its message, and the run stops. The next
  run resumes at that step; finished steps are not repeated.
- **Redo invalidates downstream.** `--redo <step>` resets that step and every step after it,
  because their output depends on it. Resetting `anchor`, for example, also resets `audio` and
  everything that follows.
- **Batch keeps going.** `--all` processes every episode in playlist order and does not stop at
  the first failure; it reports each episode and exits with `1` if any failed.
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
| `dds ingest <video_id> --redo <step>` | Resets that step and every later one, then runs. |
| `dds ingest --all` | Runs every registered episode, in playlist order. |
| `dds status` | Reads the database and prints one row per episode. |
| `dds db upgrade` | Applies migrations. Every other command does this implicitly. |
