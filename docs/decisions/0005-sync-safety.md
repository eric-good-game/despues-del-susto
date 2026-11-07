# 0005 — Sync safety: refuse suspicious listings, survive partial metadata

## Context

A sync marks every known episode missing from the listing as `unavailable`. That is correct when
the playlist really shrank, and catastrophic when the listing came back truncated: a bad response
from YouTube could mark the whole catalog as gone in one run. The pipeline also fetches metadata
one episode at a time, and a single failure should not invalidate an otherwise good sync.

## Decision

1. **Abort before writing.** If `yt-dlp` fails, returns invalid JSON, or returns zero entries, the
   sync ends with an error and the database is untouched.
2. **Refuse a truncated listing.** If fewer than `DDS_SYNC_MIN_RATIO` (default `0.5`) of the
   known available episodes appear in the listing, the sync aborts without changes.
   `--force` overrides this rule and is the only way to accept a large shrink.
3. **Metadata failure is local.** A failed full extraction records `metadata_error` on that
   episode, leaves `metadata_fetched_at` empty, and does not stop the sync or affect the other
   episodes. The next sync retries it.
4. **`--dry-run` is part of the contract.** It performs the same comparison and prints the same
   report, without writing anything and without fetching metadata.

## Consequences

- The guard needs a first successful sync to calibrate. With fewer than two known available
  episodes it is skipped, because there is no catalog to protect yet.
- A genuine mass removal requires an explicit `--force`, which leaves a trace in the command
  history. That is the intended cost.
- Metadata failures are visible in the report and in `episodes.metadata_error`, so a partial sync
  is never silent.
- The ratio is a heuristic, not proof. It is configured with `DDS_SYNC_MIN_RATIO` if 0.5 proves
  too strict or too loose.
