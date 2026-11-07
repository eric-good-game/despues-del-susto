# Glossary

Terms the code uses. It grows as phases add concepts; every term here matches an identifier in
the code or a column in the database.

| Term | Meaning |
|---|---|
| **Episode** | A video from the podcast, identified by its YouTube `video_id`. The unit the pipeline processes. |
| **`video_id`** | The stable YouTube identifier, for example `dQw4w9WgXcQ`. It is the natural key: titles and playlist positions can change, the id does not. |
| **Playlist** | The YouTube list that holds the episodes. It is the source of truth for discovery, not a fixed count. |
| **Sync** | Set-level operation that compares the playlist with the database and upserts episodes. It does not process episodes. |
| **Availability** | Whether an episode is still reachable: `available` or `unavailable`. Missing videos are marked, never deleted. |
| **Step** | One unit of the per-episode pipeline: `subs`, `anchor`, `audio`, `transcribe`, `extract`, `enrich`, `publish`. |
| **Processing** | The recorded state of each step for an episode: `pending`, `running`, `done` or `failed`, with timestamps and the last error. |
| **Artifact** | A file a step writes under `data/` (subtitles, audio, transcripts). Bulky intermediate output, not an entity. |
| **Idempotency** | Running the same command again does not repeat finished work and does not create duplicates. |
| **Run** | One invocation of `dds ingest` for one episode. A run resumes from the first step that is not `done`. |
