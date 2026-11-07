# Data model

This document describes the tables that exist today. Each phase adds its own through an Alembic
migration; the document grows with them.

Timestamps are stored in UTC.

## `episodes`

One row per video in the podcast.

| Column | Type | Notes |
|---|---|---|
| `id` | integer, primary key | Surrogate key. |
| `video_id` | text, unique | YouTube id. The natural key for upserts. |
| `title` | text | Episode title as YouTube gives it. |
| `published_at` | timestamp, nullable | Publication date. Filled by `sync`. |
| `duration_s` | integer, nullable | Duration in seconds. |
| `thumbnail_url` | text, nullable | Thumbnail URL. |
| `playlist_position` | integer, nullable | Position in the playlist, for display order only. |
| `availability` | text | `available` or `unavailable`. Only changes after an accepted sync. |
| `first_seen_at` | timestamp | When the pipeline first registered the episode. |
| `last_seen_at` | timestamp, nullable | Last accepted sync in which the episode appeared in the playlist. |
| `metadata_fetched_at` | timestamp, nullable | When date, duration and thumbnail were fetched. Empty means the next sync retries. |
| `metadata_error` | text, nullable | Last metadata failure, truncated to 2000 characters. |
| `updated_at` | timestamp | Last metadata update. |

## `processing_steps`

One row per episode and step. It is what makes runs resumable and idempotent.

| Column | Type | Notes |
|---|---|---|
| `id` | integer, primary key | |
| `episode_id` | integer, foreign key → `episodes.id` | Deleting an episode deletes its steps. |
| `step` | text | One of the seven step names. |
| `status` | text | `pending`, `running`, `done` or `failed`. |
| `started_at` | timestamp, nullable | Set when the step starts. |
| `finished_at` | timestamp, nullable | Set when it ends, successfully or not. |
| `error` | text, nullable | Last failure message, truncated to 2000 characters. |

## `episode_processing`

One row per episode, created by the first step that needs it. It holds what the steps produce,
as opposed to `processing_steps`, which only tracks orchestration.

| Column | Type | Notes |
|---|---|---|
| `episode_id` | integer, primary key, foreign key → `episodes.id` | One row per episode. |
| `subtitles_available` | boolean | Whether an automatic subtitle file was found. |
| `subtitles_language` | text, nullable | Chosen variant, for example `es`. |
| `anchor_s` | integer, nullable | Second where the recommendations section starts. |
| `anchor_kinds` | text, nullable | Detected signals, comma-separated: `intro`, `juego`, `peli`. |
| `anchor_state` | text, nullable | `ok`, `parcial` or `sin_ancla`. |
| `anchor_evidence` | text, nullable | *Internal.* Fragment that triggered the detection, for review. |
| `tail_s` | integer, nullable | Seconds from the anchor to the end of the episode. |
| `updated_at` | timestamp | |

The audio window, transcription provider and extraction model are added to this table in their
phases.

## Integrity rules

- `episodes.video_id` is unique. An episode exists once, no matter how many times sync sees it.
- `(episode_id, step)` is unique. A step has one state per episode.
- Deleting an episode cascades to its steps.
- `availability` changes only after a listing that the safety check accepted. A failed or
  suspicious sync leaves every episode as it was.
- `title` is written by the playlist listing, never by the full metadata extraction.
- `metadata_fetched_at` is empty until date, duration and thumbnail are stored; a failed attempt
  records `metadata_error` and leaves it empty so the next sync retries.
- A step can only move `pending → running → done | failed`. A retry puts a failed step back to
  `running`.
- An episode has at most one `episode_processing` row, created lazily by the first step that
  writes to it.
- `subtitles_available = false` implies `anchor_state = sin_ancla`.
- `anchor_state` is `ok`, `parcial` or `sin_ancla` once the anchor step has run, and empty before.
- `anchor_evidence` is internal and never published.
- The derived state of an episode is not stored: it is computed from its steps (`not started`,
  `in progress`, `failed`, `complete`).

## Not defined yet

`works`, `recommendations`, `availability` of works, candidates and publication data. They arrive
with the phases that need them. The audio window fields will join `episode_processing` in phase 4.
