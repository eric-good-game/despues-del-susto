# 0013 — Enrichment: TMDB and IGDB, similarity with a year tie-break

## Context

Extraction leaves one row per recommendation with a mentioned title, a probable title and a
confidence. The catalog needs real works with official titles, years, genres, images and source
links. TMDB and IGDB provide them with free, non-commercial APIs. The prototype had no enrichment,
so this phase defines the matching contract.

## Decision

- **Sources by type:** movies and series in TMDB, videogames in IGDB. Books and `other` are
  `manual_pending`; there is no automatic source for them.
- **Labeled queries for every stated title.** `mentioned`, `corrected`, `probable` and each
  `alternate` title are searched (TMDB as movie and series, in `es-MX` and `en-US`), deduplicated
  literal-first. Separating the transcription fix (`corrected`), the semantic re-identification
  (`probable`) and the **host-stated aliases/translations** (`alternate`) lets enrichment know *where*
  a match came from. The Huesera case showed searching only in Spanish misses the English title;
  `"Other Mother"` vs `"Other Mommy / Madre siniestra (2026)"` showed the reverse: the audio names
  the Spanish title explicitly, and capturing it as an `alternate` is what finds the right work.
- **Provenance.** Each candidate keeps the most literal label that scores it (`mentioned` >
  `corrected` > `probable`), recorded as `from_*`. A literal match is trusted; a probable-only match
  is a guess and is held to a higher bar. This is what fixes the `"No vayas a casa"` / `"Don't Come
  Home"` false `uncertain_title`: the Spanish mention now matches the localized catalog title, so the
  origin is literal.
- **Local title variants.** Each query is expanded with article removal, trailing number removal
  and a small dictionary of known translations. Keyword fragments are avoided because short fragments
  match unrelated titles and create false ties. Candidates are scored against the best variant.
- **Unfiltered provider search.** The year is not sent to the API as a filter; a wrong or
  approximate year drops the correct candidate. Year, genre and the disambiguation phrase only break
  ties afterward.
- **Disambiguation phrase.** Extraction may store a `disambiguation` string — the host's own words
  that identify which version is meant ("la más viejita", "la coreana", "la del 2007 o por ahí") —
  only when said. Enrichment reads era, country and approximate-year signals from it to settle
  same-title ties. A colloquial year stays here, not in `year`.
- **Tie-breaking by type, genre, era, country, year, popularity.** For candidates within `0.05`:
  same-medium (`resolved_by_type`, shorts yielding to features), a single horror-family genre
  (`resolved_by_genre`), era and country words from the hint (`resolved_by_era`,
  `resolved_by_country`), an explicit year within ±1 (`resolved_by_year`) or a hint year within ±2
  (`resolved_by_hint_year`), then the most popular (`resolved_by_popularity`, always flagged). A
  wrong-medium-only match is kept with `type_substituted`; `low` confidence is overridden when the
  hint settles the version.
- **Score with `rapidfuzz`** over the normalized title and original title, taking the best. It
  handles word order and accents better than `difflib`.
- **Guards:** a `low` confidence, or a **probable-only** title that does not resemble the chosen
  work, sends the recommendation to review — unless the match is literal, the `disambiguation` phrase
  settles the version, or the probable resolves to a real catalog work at similarity `>= 0.90`
  (`probable_strong`), which trusts a correct translation such as "No vayas a casa" → "Don't Come
  Home".
- **One work per `(source, external_id)`.** Confirmed matches upsert the work and fetch its details,
  storing year, genres, `original_language` and `origin_country` for the future catalog display;
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
