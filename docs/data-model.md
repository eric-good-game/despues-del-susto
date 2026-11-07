# Data model

Phase 1 defines only the tables the walking skeleton needs. Each later phase adds its own tables
through an Alembic migration; this document grows with them.

Timestamps are stored in UTC.

## `episodes`

One row per video in the podcast.

| Column | Type | Notes |
|---|---|---|
| `id` | integer, primary key | Surrogate key. |
| `video_id` | text, unique | YouTube id. The natural key for upserts. |
| `title` | text | Episode title as YouTube gives it. |
| `published_at` | timestamp, nullable | Publication date. Filled by `sync` in phase 2. |
| `duration_s` | integer, nullable | Duration in seconds. |
| `thumbnail_url` | text, nullable | Thumbnail URL. |
| `playlist_position` | integer, nullable | Position in the playlist, for display order only. |
| `availability` | text | `available` or `unavailable`. |
| `first_seen_at` | timestamp | When the pipeline first registered the episode. |
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

## Integrity rules

- `episodes.video_id` is unique. An episode exists once, no matter how many times sync sees it.
- `(episode_id, step)` is unique. A step has one state per episode.
- Deleting an episode cascades to its steps.
- A step can only move `pending → running → done | failed`. A retry puts a failed step back to
  `running`.
- The derived state of an episode is not stored: it is computed from its steps (`not started`,
  `in progress`, `failed`, `complete`).

## Not defined yet

`works`, `recommendations`, `availability` of works, candidates and publication data. They arrive
with the phases that need them.
