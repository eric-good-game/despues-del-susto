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
| `audio` | Download the audio window. | `video_id` and window start | `data/audio/<video_id>.mp3` and the window start in the database | Real |
| `transcribe` | Turn the audio window into text with seconds. | Audio and window start | `data/transcripts/<video_id>.json` and `.txt` | Real |
| `extract` | Pull recommendations out of the transcript. | Transcript | `data/extractions/<video_id>.json` and recommendation rows | Real |
| `enrich` | Match each work, fetch its details and store the catalog work. | Recommendations | `works`, `candidates` and match state in the database | Real |
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

### Audio

The audio step turns the anchor into a window and downloads only that section.

- The window rules are `BR-09` to `BR-13` in [`rules.md`](rules.md). The start is stored in
  `episode_processing.window_start_s` and the reason in `window_origin`.
- Command: `yt-dlp --download-sections "*<start>-inf" -x --audio-format mp3 --audio-quality 48K
  --force-keyframes-at-cuts --force-overwrites`.
- **48 kbps** keeps even the largest window under the 25 MB transcription limit. A higher bitrate
  would push a 40-minute window over it.
- **`--force-keyframes-at-cuts`** makes the cut accurate. Without it the audio can start seconds
  before or after the requested second, and the offset used by the transcription becomes wrong.
- Artifact: `data/audio/<video_id>.mp3`. Partial files are removed when a download fails.
- Missing `duration` or anchor data fails with a clear message; the step does not fetch metadata on
  its own. `--redo audio` downloads the section again.

### Transcription

The transcription step sends the audio window to Groq and stores the text with episode seconds.

- Model: `whisper-large-v3` in Spanish, `verbose_json`, segment timestamps.
- **One request per episode.** The 48 kbps window stays under the 25 MB limit; the step fails
  instead of uploading a larger file.
- Each segment is stored as `segment start + window_start_s`, so transcript times are real episode
  seconds and can be compared with the anchor.
- Artifacts: `data/transcripts/<video_id>.json` (list of `{t, text}`) and
  `data/transcripts/<video_id>.txt` (human-readable). Both are written atomically.
- Transient errors (429, 5xx, timeouts) are retried with waits of 5, 15, 45 and 90 seconds. A rate
  limit or exhausted quota after the retries raises `StopBatch`: the step stays `pending` and the
  batch stops. Credential and validation errors fail immediately.
- A transcription with zero segments is a failure, not an empty success.
- Local `faster-whisper` is not wired yet; it stays as a fallback decision for later.

### Extraction

The extraction step asks a chat model for the recommendations and stores them.

- **Provider:** `PROVIDER` selects `gemini`, `groq` or `opencode`. Each has its own key, model and
  fallback list; Groq uses `GROQ_CHAT_MODEL` because `GROQ_MODEL` belongs to transcription.
- **One call per episode**, temperature `0`, with the transcript as `[t=<second>] text` lines.
- The prompt is in Spanish because the content is Spanish; the JSON keys and values are in English
  (`type`, `mentioned_title`, `confidence`, `videogame`, `movie`…).
- Invalid JSON is retried; transient errors are retried with the same 5/15/45/90 second waits; a
  rate limit or exhausted quota raises `StopBatch` and leaves the step `pending`.
- The step assigns roles, computes completeness warnings and stores one row per recommendation in
  the `recommendations` table.
- Artifact: `data/extractions/<video_id>.json` with the provider, model, `declared_count`,
  `complete`, `warnings` and the normalized recommendations.
- `--redo extract` replaces the automatic recommendations of the episode. Manual decisions are not
  overwritten when review arrives.
- There is **no expanded-window retry**: an incomplete extraction is recorded and left for review.

### Enrichment

The enrichment step matches each extracted recommendation against the metadata providers.

- **Sources by type:** movies and series in TMDB, videogames in IGDB. Books and `other` go to
  `manual_pending` without a call.
- **Search both sides.** A movie or series recommendation is searched in TMDB as a movie and as a
  series, and in `es-MX` and `en-US`, because the model's probable title may be the localized or
  the original one.
- **Scoring:** normalized title similarity against the candidate's title and original title, taking
  the best. Threshold `0.85`; below it, `needs_review`.
- **Tie-breaking:** when the top two are within `0.05`, a year hint within ±1 year resolves it;
  otherwise it goes to review. The `Devil May Cry (2001)` case is the reference.
- **Guards:** low confidence and a mentioned title that does not resemble the chosen work go to
  review even when the score is high.
- **Confirmed** creates or reuses a work by `(source, external_id)`, fetches its details and links
  the recommendation. Up to 5 candidates are stored on every recommendation.
- **Cache and pacing:** provider responses are cached under `data/cache/`; IGDB calls are spaced by
  `DDS_IGDB_DELAY_S`. A rate limit raises `StopBatch`.
- Re-enriching replaces automatic candidates and matches, and removes works that no recommendation
  points to.
- Availability is **not** part of this step yet; it arrives in phase 7b.

## Orchestration

- **Resumable.** A run skips every step whose state is `done`. The first step that is not `done`
  runs, and the rest follow in order.
- **Fail fast.** A failing step is marked `failed` with its message, and the run stops. The next
  run resumes at that step; finished steps are not repeated.
- **Unimplemented steps stop cleanly.** A step with no implementation ends the run, stays
  `pending` and is never marked `done`, so implementing it later does not require a reset.
- **Redo invalidates downstream.** `--redo <step>` resets that step and every step after it,
  because their output depends on it. Resetting `anchor`, for example, also resets `audio` and
  everything that follows.
- **Batch keeps going on failures.** `--all` reports a failed episode and continues with the next,
  and the command exits with `1` at the end.
- **Batch advances by itself.** Without `--redo`, `--all` selects episodes where the last
  implemented step is not `done`, in playlist order. `--limit N` caps the batch, so rerunning the
  same command moves through the catalog.
- **A stop signal ends the batch.** If a step raises `StopBatch` (for example, an exhausted API
  quota), the step stays `pending`, the batch stops and the remaining episodes are untouched.
- **Output streams.** A single-episode run writes its step lines to stdout. Batch and sync progress
  go to stderr, keeping stdout for the final report. `--quiet` suppresses progress.
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
  transcripts/<video_id>.txt
  extractions/<video_id>.json
  cache/<provider>/
```

The database is the source of truth for state. An artifact may be regenerated; a step's recorded
state is what decides whether it runs again. The audio offset lives in the database, not in a
sidecar CSV file.

## Commands

| Command | Contract |
|---|---|
| `dds sync` | Set-level discovery. |
| `dds episode add <video_id> --title ...` | Manual registration, no network. |
| `dds ingest <video_id>` | Runs the steps, resuming where needed. Writes step progress to stdout. |
| `dds ingest <video_id> --redo <step>` | Resets that step and every later one, then runs. |
| `dds ingest --all` | Runs pending episodes through the last implemented step. |
| `dds ingest --all --limit N` | Same, for the first N pending episodes. |
| `dds --quiet …` | Suppresses progress; final reports still print. |
| `dds sync` | Set-level discovery. Progress goes to stderr. |
| `dds status` | Reads the database and prints one row per episode. |
| `dds db upgrade` | Applies migrations. Every other command does this implicitly. |
