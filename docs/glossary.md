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
| **Window** | The audio section that is downloaded and transcribed: from the window start to the end of the episode. |
| **Window start** | Second where the downloaded audio begins. It is added to the transcript times to get real episode seconds. |
| **Window origin** | Why that start was chosen: `anchor` or `fallback`. |
| **Margin** | Seconds downloaded before the anchor so the start of the section is not cut off. It depends on the anchor state. |
| **Fallback** | The window used when there is no anchor: the last 45 % of the episode, capped at 1500 s. |
| **Transcript** | Text with seconds produced by the transcription step. Stored as JSON and TXT; internal and never published. |
| **Segment** | One timed line of the transcript: a start second and its text. |
| **Provider** | External service that performs a job for the pipeline: Groq for transcription, TMDB and IGDB for enrichment. |
| **Quota** | Usage limit of a free tier. When it is exhausted, the step stops the batch instead of failing every remaining episode. |
| **Recommendation** | A work mentioned explicitly as a suggestion in an episode. It links one episode with one work. |
| **Extraction** | The step where the model reads the transcript and returns the recommendations in structured form. |
| **Role** | `primary` for the expected videogame and movie; `additional` for a series, a book or an extra work. |
| **Confidence** | The model's certainty about an extracted recommendation: `high`, `medium` or `low`. |
| **Declared count** | How many recommendations the audio says it has. Used to detect missing ones. |
| **Completeness** | Whether the episode has the expected primary works. It is recorded as warnings, not as a failure. |
| **Warning** | A code in the extraction describing a gap, such as `missing_videogame` or `fewer_than_declared`. |
| **Work** | A catalog entry resolved against TMDB or IGDB: a videogame, movie or series. |
| **Match** | The connection between a recommendation and a work, made by comparing titles. |
| **Score** | Similarity between the query and a candidate, from 0 to 1. Internal. |
| **Candidate** | A possible match returned by a provider, stored for review when the decision is not clear. |
| **Source** | The provider a work comes from: `TMDB`, `IGDB` or `manual`. |
| **Review** | The manual pass where doubtful matches are resolved, corrected or discarded. |
| **Manual decision** | A choice made by the author during review; enrichment never overwrites it. |
| **Manual work** | A work entered by hand, usually a book or an `other` type without an automatic source. |
| **Discard** | Marking a recommendation as not a real recommendation; it is kept for history and not published. |
| **Availability** | Whether an episode is still reachable: `available` or `unavailable`. Missing videos are marked, never deleted. |
| **Step** | One unit of the per-episode pipeline: `subs`, `anchor`, `audio`, `transcribe`, `extract`, `enrich`, `publish`. |
| **Processing** | The recorded state of each step for an episode: `pending`, `running`, `done` or `failed`, with timestamps and the last error. |
| **Artifact** | A file a step writes under `data/` (subtitles, audio, transcripts). Bulky intermediate output, not an entity. |
| **Idempotency** | Running the same command again does not repeat finished work and does not create duplicates. |
| **Run** | One invocation of `dds ingest` for one episode. A run resumes from the first step that is not `done`. |
| **Batch** | One invocation of `dds ingest --all`, optionally capped with `--limit`. It processes pending episodes in playlist order. |
| **Target step** | The last step that has an implementation. A batch selects episodes where it is not `done`, so the target advances when a phase implements the next step. |
| **Pending** | An episode has not finished the target step. Only pending episodes are selected by a batch. |
