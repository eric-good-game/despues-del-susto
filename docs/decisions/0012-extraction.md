# 0012 — Extraction: one chat call per episode, Spanish prompt, English data

## Context

The transcript is written with real episode seconds. The extraction must turn it into structured
recommendations without inventing works, and the result has to be stable enough to persist and
match later. The previous prototype validated a prompt and a completeness check against the
podcast. The configured chat provider in this environment is OpenCode; Gemini and Groq are
available through the same OpenAI-compatible interface.

## Decision

- **Provider from configuration.** `PROVIDER` selects `gemini`, `groq` or `opencode`, with its own
  key, model and fallback list. Groq uses `GROQ_CHAT_MODEL`, because `GROQ_MODEL` is the
  transcription model.
- **One chat call per episode**, temperature `0`, with the transcript as `[t=<second>] text` lines.
- **Spanish prompt, English data.** The instructions stay in Spanish because the content and the
  validated wording are Spanish; the JSON keys and values are English (`type`, `mentioned_title`,
  `confidence`, `videogame`, `movie`), matching the project's data language.
- **Roles and warnings are computed in code**, not trusted to the model. The first videogame and
  first movie are primary; a series can replace the movie; the rest are additional.
- **One row per recommendation** in the `recommendations` table, with `state = extracted` and
  `decided_by = automatic`.
- **Re-running replaces automatic rows** for the episode. Manual rows are left alone; manual review
  arrives in a later phase.
- **No expanded-window retry.** An incomplete extraction is recorded with warnings and left for
  review. The larger audio window was considered and dropped for this version.
- **Same retry policy as transcription:** invalid JSON and transient errors are retried; a rate
  limit or exhausted quota raises `StopBatch` and leaves the step `pending`.

## Alternatives considered

- **English prompt.** It saves a marginal number of prompt tokens, but the transcript dominates the
  request and the Spanish prompt was the validated one.
- **One call per work.** More calls, more cost, and no clear gain: the model needs the surrounding
  conversation to tell a recommendation from a passing mention.
- **Store only the artifact and defer the database.** Simpler for one phase, but then enrichment and
  review would have to read files instead of rows, and redo semantics would be weaker.
- **Let the model decide roles.** It already confuses movie and series; roles are deterministic and
  belong in code.
- **Expanded-window retry.** It chains audio, transcription and extraction again. There is no
  evidence yet that the extra cost is worth it.

## Consequences

- Extraction quality depends on the model and the transcript. Low-confidence and incomplete results
  are visible as warnings instead of silent failures.
- The `recommendations` table becomes the working surface for enrichment and review.
- A redo discards automatic recommendations but preserves manual decisions, which is the behavior
  the review phase needs.
- The artifact keeps the raw normalized result for debugging without querying the database.
