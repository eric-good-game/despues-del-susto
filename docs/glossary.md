# Glossary

Terms the code uses. It grows as phases add concepts; every term here matches an identifier in
the code or a column in the database.

| Term | Meaning |
|---|---|
| **Episode** | A video from the podcast, identified by its YouTube `video_id`. The unit the pipeline processes. |
| **`video_id`** | The stable YouTube identifier, for example `dQw4w9WgXcQ`. It is the natural key: titles and playlist positions can change, the id does not. |
| **Playlist** | The YouTube list that holds the episodes. It is the source of truth for discovery, not a fixed count. |
| **Sync** | Set-level operation that compares the playlist with the database and upserts episodes. It does not process episodes. |
| **Flat listing** | The playlist read with `yt-dlp --flat-playlist`: order, `video_id` and title, without per-video extraction. |
| **Metadata fetch** | One full extraction for an episode to get its date, duration and thumbnail. Runs only when `metadata_fetched_at` is empty. |
| **Truncated listing** | A listing that is empty, or much smaller than the known catalog. It is refused unless `--force` is passed. |
| **Sync report** | The counts and ids a sync prints: added, updated, unavailable, reactivated, unchanged, metadata fetched and failed. |
| **Auto subtitles** | The captions YouTube generates for an episode. Downloaded as `json3`, the only format the anchor step reads. |
| **Rolling captions** | The way auto subtitles repeat a line as it grows word by word. The repeated prefixes are dropped before matching. |
| **Anchor** | The second where the recommendations section starts, found in the subtitles. Internal; it is not published. |
| **Anchor kinds** | Which signals were detected: `intro`, `juego`, `peli`. |
| **Anchor state** | `ok` when both game and movie signals appear, `parcial` when one is missing, `sin_ancla` when none. |
| **Tail** | Seconds from the anchor to the end of the episode. |
| **Evidence** | The subtitle fragment that triggered a detection, stored to review doubtful cases. Internal. |
| **Availability** | Whether an episode is still reachable: `available` or `unavailable`. Missing videos are marked, never deleted. |
| **Step** | One unit of the per-episode pipeline: `subs`, `anchor`, `audio`, `transcribe`, `extract`, `enrich`, `publish`. |
| **Processing** | The recorded state of each step for an episode: `pending`, `running`, `done` or `failed`, with timestamps and the last error. |
| **Artifact** | A file a step writes under `data/` (subtitles, audio, transcripts). Bulky intermediate output, not an entity. |
| **Idempotency** | Running the same command again does not repeat finished work and does not create duplicates. |
| **Run** | One invocation of `dds ingest` for one episode. A run resumes from the first step that is not `done`. |
