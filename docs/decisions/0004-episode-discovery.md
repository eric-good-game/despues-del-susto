# 0004 — Episode discovery from the YouTube playlist

## Context

The playlist currently holds 50 episodes and will keep growing. The catalog cannot hardcode that
number, and reprocessing an episode that is already registered is wasted work. Discovery also runs
from a residential connection, where YouTube is less likely to block requests.

## Decision

- **Source:** the podcast playlist, read with `yt-dlp --flat-playlist`. No API key and no quota.
- **Natural key:** `video_id`. Titles, positions and thumbnails may change; the id does not.
- **Upsert, never delete.** Episodes missing from the playlist are marked `unavailable`, keeping
  their data and their processing state.
- **Metadata for new episodes only.** The flat listing gives ids and titles; the full extraction
  (date, thumbnail, duration) runs only for episodes that did not exist yet.
- **Manual for now.** `dds sync` is run by hand. Scheduling it is part of the operations phase.
- **`sync` does not ingest.** Discovery and processing stay separate commands.

## Alternatives considered

- **YouTube Data API v3.** Official and richer, but requires a key and consumes quota, and adds
  nothing this project needs. Reversible if blocking becomes a problem.
- **Channel RSS feed.** Cheap and gives dates, but only the latest 15 videos, and the playlist is
  already the user's source of truth.
- **Automatic sync on every ingest.** Hides network calls inside a command that should be
  repeatable offline. Discarded.

## Consequences

- The catalog reflects the playlist at the time of the last sync, which is exactly what a manual
  local tool needs.
- Non-episode entries (a clip, an announcement) are not guessed away; they are listed and the
  author decides whether to ingest them.
- If the playlist is renamed or replaced, only `DDS_PLAYLIST_URL` changes.
