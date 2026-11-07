# 0013 — Enrichment: TMDB and IGDB, similarity with a year tie-break

## Context

Extraction leaves one row per recommendation with a mentioned title, a probable title and a
confidence. The catalog needs real works with official titles, years, genres, images and source
links. TMDB and IGDB provide them with free, non-commercial APIs. The prototype had no enrichment,
so this phase defines the matching contract.

## Decision

- **Sources by type:** movies and series in TMDB, videogames in IGDB. Books and `other` are
  `manual_pending`; there is no automatic source for them.
- **Search both TMDB types and both languages.** A movie or series is searched as a movie and as a
  series, in `es-MX` and `en-US`. The model's probable title may be localized or original; the
  Huesera case showed that searching only in Spanish misses the English title.
- **Score with `rapidfuzz`** over the normalized title and original title, taking the best. It
  handles word order and accents better than `difflib`.
- **Thresholds:** `0.85` to confirm, `0.05` minimum difference between the top two. A year hint
  within ±1 year breaks a tie; without it, the case goes to review.
- **Guards:** low confidence, type mismatch, and a mentioned title that does not resemble the
  chosen work send the recommendation to review.
- **One work per `(source, external_id)`.** Confirmed matches upsert the work and fetch its details;
  candidates are stored for review, up to 5 per recommendation.
- **Re-enrichment replaces** automatic candidates and matches and removes works that no longer have
  a recommendation.
- **No subtitle cross-check yet.** If the catalog pass shows many `no_match` cases, the second
  source is the next step.
- **No availability yet.** That is the availability phase, with its own tables and API calls.

## Alternatives considered

- **Let the LLM match titles directly.** It would add a second probabilistic step on top of the
  extraction, with no deterministic score to review or tune.
- **Only search the probable title in Spanish.** Faster, but the Huesera case proves it misses
  works whose TMDB title is the original English one.
- **Use `difflib`.** No dependency, but worse on accents, word order and short titles.
- **Confirm everything above the threshold without guards.** The `Other Mother` case shows a
  probable title can be an exact match for the wrong work; the guards and review exist for that.
- **Store the provider payload.** The normalized work and candidate rows are enough; the cache
  keeps the raw response for debugging.

## Consequences

- The catalog is built from APIs, so attribution and the source terms become part of the site; see
  [`sources.md`](../sources.md).
- A wrong probable title can still confirm a wrong work when the score and confidence align. The
  review phase and the `match_note` are the safety net.
- Re-running enrichment is cheap thanks to the cache, but it is still an API pass; the step is
  repeatable and replaces candidates instead of duplicating them.
- Works are shared across episodes: two episodes recommending the same movie point to one row.
