# Rules

Business rules carry a `BR-xx` id so code, tests and documentation can cite the same thing.
Parameters are the numbers those rules use; if a value changes, it changes here first.

Origin: **Decision** means the author decided it. **Initial** means a starting value that will be
measured and adjusted with real episodes.

## Parameters

| Parameter | Value | Used by |
|---|---|---|
| Minimum anchor position | `0.5` (second half of the episode) | BR-01 |
| Maximum distance from the anchor to the end | `720` s | BR-02 |
| Margin with an `ok` anchor | `90` s | BR-09 |
| Margin with a `parcial` anchor | `240` s | BR-10 |
| Short-tail threshold | `150` s | BR-10 |
| Margin with a `parcial` anchor and a short tail | `420` s | BR-10 |
| Fallback share when there is no anchor | `0.45` of the episode | BR-11 |
| Fallback cap | `1500` s | BR-11 |
| Transcription model | `whisper-large-v3` | BR-16 |
| Maximum audio upload | 25 MB (provider limit) | BR-19 |
| Transcription retry waits | 5, 15, 45, 90 s | BR-20 |
| Match threshold | `0.85` | BR-35 |
| Minimum difference between the top two candidates | `0.05` | BR-37 |
| Year tolerance for tie-breaking | `1` year | BR-37 |
| Maximum stored candidates per recommendation | `5` | BR-41 |
| TMDB search languages | `es-MX` and `en-US` | BR-33 |
| IGDB request spacing | `0.26` s | BR-40 |

## Anchor detection

| ID | Rule | Origin |
|---|---|---|
| BR-01 | A candidate match only counts if it falls in the second half of the episode. | Initial |
| BR-02 | A candidate match only counts if it is at most 720 s from the end of the episode. | Initial |
| BR-03 | Among the kinds detected, the earliest one sets `anchor_s`; the others are kept in `anchor_kinds`. | Initial |
| BR-04 | The state is `ok` when both `juego` and `peli` appear, `parcial` when at least one appears and the other does not, and `sin_ancla` when none appear. | Initial |
| BR-05 | Without a subtitle file, the anchor step succeeds with `subtitles_available = false` and `anchor_state = sin_ancla`. The audio step uses its fallback. | Decision |
| BR-06 | One subtitle language per episode. Preference: `es`, `es-orig`, `es-419`, `es-mx`, `es-es`, then any other `es*`. Non-chosen files are deleted. | Initial |
| BR-07 | Rolling-caption prefixes are dropped before matching, so the same sentence is not counted several times. | Initial |
| BR-08 | Anchor data and evidence are internal. They are used to review a detection and are never published. | Decision |

## Audio window

| ID | Rule | Origin |
|---|---|---|
| BR-09 | With an `ok` anchor, the window starts 90 s before it and reaches the end of the episode. | Initial |
| BR-10 | With a `parcial` anchor, the margin is 240 s. If the tail is shorter than 150 s, the margin is 420 s. | Initial |
| BR-11 | Without an anchor, the window is the last 45 % of the episode, capped at 1500 s. | Initial |
| BR-12 | The window start is never below 0, and the window always reaches the end of the episode. | Decision |
| BR-13 | `window_origin` records why the window was chosen: `anchor` or `fallback`. | Decision |
| BR-14 | The expanded window (last 60 %, capped at 2400 s) was considered and is **not implemented**. There is no automatic retry with a larger window in this version. | Decision |
| BR-15 | Audio is downloaded and kept only for analysis. It is never published, uploaded or shared. | Decision |

## Transcription

| ID | Rule | Origin |
|---|---|---|
| BR-16 | Transcription uses Groq with the `whisper-large-v3` model and language `es`. | Decision |
| BR-17 | The transcript is internal. It is never published, in whole or in part. | Decision |
| BR-18 | Every segment is stored in real episode seconds: the segment start plus `window_start_s`. | Decision |
| BR-19 | One request per episode. If the audio file exceeds the provider's 25 MB limit, the step fails instead of uploading it. | Decision |
| BR-20 | Transient errors (429, 5xx, timeouts) are retried. A rate limit or exhausted quota after the retries stops the batch and leaves the step `pending`. Credential and validation errors are not retried. | Initial |
| BR-21 | The step writes a JSON transcript and a human-readable TXT. A transcription with zero segments is a failure. | Decision |

## Extraction

| ID | Rule | Origin |
|---|---|---|
| BR-22 | Only an explicit mention of a work as a suggestion counts. Works commented on in passing are not extracted. | Decision |
| BR-23 | The expected format is 1 videogame and 1 movie; a series, a book or an extra movie are additional works. | Decision |
| BR-24 | Roles: the first videogame and the first movie are `primary`; everything else is `additional`. If there is no movie, the first series takes the primary place and gets the `series_in_place_of_movie` warning. | Decision |
| BR-25 | Sequels, spin-offs and related series named alongside a work go to `related_mentions`; they do not create separate rows unless offered as a new recommendation. | Initial |
| BR-26 | Confidence is `high`, `medium` or `low`. Low confidence is expected to go to review during enrichment. | Initial |
| BR-27 | When the audio declares a number of recommendations, it is stored as `declared_count`. Extracting fewer adds `fewer_than_declared`. | Initial |
| BR-28 | The `type` returned by the model is a hypothesis; the final type comes from the enrichment match. | Initial |
| BR-29 | The extraction and its artifact are internal. They are never published. | Decision |
| BR-30 | Re-running the step replaces automatic recommendations for the episode. Manual decisions are not overwritten; manual review arrives in a later phase. | Decision |
| BR-31 | Completeness is recorded as warnings, not as a step failure. No expanded-window retry exists in this version. | Decision |

## Enrichment

| ID | Rule | Origin |
|---|---|---|
| BR-32 | Movies and series are searched in TMDB both as movies and as series. Videogames are searched in IGDB. Books and `other` go to `manual_pending` without an API call. | Decision |
| BR-33 | The query is `probable_title`, or `mentioned_title` when the probable one is empty. A trailing parenthetical is removed; a year inside the title is kept as a hint. TMDB is searched in `es-MX` and `en-US` to cover both localized and original titles. | Initial |
| BR-34 | The score is the maximum similarity between the normalized query and the candidate's title or original title, from 0 to 1. | Initial |
| BR-35 | A score of `0.85` or more is `confirmed`; below it is `needs_review`; no candidates is `no_match`. | Initial |
| BR-36 | A recommendation with `low` confidence goes to `needs_review` even if the score is high. | Initial |
| BR-37 | If the two best candidates differ by less than `0.05`, a year hint within ±1 year breaks the tie. If it still does not resolve, the recommendation goes to `needs_review`. | Initial |
| BR-38 | If the chosen candidate's type differs from the extracted type, the recommendation goes to `needs_review`. | Initial |
| BR-39 | If confidence is not `high` and the mentioned title does not resemble the chosen work (similarity below `0.5`), the recommendation goes to `needs_review` with `uncertain_title`. | Initial |
| BR-40 | A confirmed recommendation creates or reuses one work per `(source, external_id)`, fetches its details and stores title, original title, year, genres, description, image and source URL. | Decision |
| BR-41 | Up to 5 candidates are stored per recommendation. On a confirmed match, the chosen one is marked. | Initial |
| BR-42 | Re-enriching replaces the recommendation's automatic candidates and match, and removes works that no recommendation points to. | Decision |
| BR-43 | Match scores, notes, candidates and the mention second are internal. They are never published. | Decision |
| BR-44 | Prices are never stored or shown. Availability arrives with its own phase. | Decision |

## How the initial values are validated

After processing the 50 existing episodes, measure:

- The distribution of `ok`, `parcial` and `sin_ancla`.
- How many `ok` detections point at a plausible section when checked by hand.
- How many anchors would cut off the start of the section, which is what the margin in the audio
  step will correct.

With that, adjust BR-01 and BR-02 before touching the margins.

After the first 5 to 10 windows are downloaded, also check:

- How many episodes used `fallback` instead of an anchor.
- Whether the margins are larger than needed: how far before the anchor the section actually
  starts in the audio.
- Whether any window exceeds the transcription size limit. If so, BR-14 or the transcription
  chunking will absorb it.

After the first 3 to 5 transcripts, also check:

- How often proper names come out wrong; that is the error the subtitle cross-check exists for.
- The elapsed time per episode, to plan batches around the quota.
- Whether the offsets land on the expected lines when compared with the anchor.

After the first 5 to 10 extractions, also check:

- How many roles are assigned correctly (one game and one movie as primary).
- How often a work is extracted from a passing mention rather than a recommendation.
- The distribution of warning codes, especially `missing_videogame` and `missing_movie`.
- Whether the probable titles are good enough for enrichment to match automatically.

After the first catalog pass, also check:

- The distribution of `confirmed`, `needs_review`, `no_match` and `manual_pending`.
- Which confirmed matches are wrong when reviewed by hand; that is the number the threshold and the year rule must reduce.
- How often the year tie-break resolves what would otherwise be a close call.
- Whether the `uncertain_title` guard sends cases that were actually correct to review.
