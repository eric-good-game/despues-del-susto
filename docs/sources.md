# Sources and attribution

Every published datum has a source, and the site must show it. This document records where each
piece comes from, what attribution it requires, and what the pipeline deliberately does not store.
It is not legal advice; the terms of each service must be checked again before publishing.

## 1. Where the data comes from

| Published datum | Source | How the pipeline gets it |
|---|---|---|
| Episode title, date, thumbnail, video | YouTube | `yt-dlp` metadata |
| Movie and series title, year, genres, poster, description | TMDB | TMDB API |
| Movie and series availability in Mexico | JustWatch, through TMDB | TMDB watch providers (phase 7b) |
| Videogame title, year, genres, cover, description | IGDB | IGDB API |
| Videogame store links | IGDB | IGDB websites (phase 7b) |
| Recommendation itself: which work in which episode | The episode | Transcript extraction and review |

## 2. Attribution

### TMDB

- Required notice, visible in the About page and credits: **"This product uses the TMDB API but is
  not endorsed or certified by TMDB."**
- Use an approved TMDB logo, unmodified, less prominent than the site's own mark.
- Call it "TMDB" or "The Movie Database" and link to <https://www.themoviedb.org>.
- Do not suggest that TMDB endorses the project.
- The API is free for non-commercial use. This project has no ads, affiliates or revenue.
- Images are served from TMDB's image network; whether copies may be stored is **to verify** before
  publishing.

Status: requirement known; exact logo asset and caching rules **to verify**.

### JustWatch

- Movie availability comes from JustWatch through TMDB. TMDB's documentation asks to credit
  JustWatch.
- The exact text and logo format are **to verify**.
- Each availability datum must show its last-updated date.

Placeholder until verified: "Movie availability: JustWatch, via TMDB. Consulted on [date]."

### IGDB and Twitch

- Videogame data comes from the IGDB API, under the Twitch Developer Services Agreement.
- Voluntary attribution: **"Videogame data: IGDB"**, linked to <https://www.igdb.com>.
- The Twitch agreement, rate limits and caching rules are **to verify** before publishing.
- Store links are not specific to Mexico and are shown without prices.

### YouTube

- Episodes are linked or embedded from the start of the video. No `&t=` and no visible timestamps.
- If a video cannot be embedded, only the link is shown.
- Audio and subtitles are downloaded only for analysis, locally, and are never published.
- YouTube's terms on embedded players and on downloading content are **to verify** before
  publishing.

## 3. What is stored and what is not

Stored in the catalog: source identifier, official and original title, year, genres, description
allowed by the source, image URL, source page URL and availability.

Not stored or published:

- Prices.
- Audio, transcripts, subtitles or fragments of them.
- Anchor seconds, mention seconds, match scores, candidates and evidence.
- Copied synopses from other sites; only what the API provides or a short original summary.
- Scraped pages. All provider data comes from its API.

## 4. Site notices

The About page and the footer must include:

- The unofficial fan-project notice, with no relation to the podcast or its owner.
- The non-commercial notice.
- The source list above, with links.
- The TMDB notice and approved logo.
- A contact address for changes or removal requests.
- The horror-content or age-rating notice, still **pending**.

## 5. Checklist before publishing

- [ ] Read the current TMDB API terms, rate limits, caching and image rules.
- [ ] Confirm the JustWatch attribution text and format.
- [ ] Obtain the approved TMDB logo.
- [ ] Read the Twitch Developer Services Agreement and IGDB terms.
- [ ] Read YouTube's terms for embedded players and downloads.
- [ ] Decide whether images are linked or copied, per each source.
- [ ] Write the About page with a working contact.
- [ ] Decide the horror-content notice.
- [ ] Confirm that nothing from section 3 is visible on the site.
