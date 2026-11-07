# 0010 — Transcription: Groq `whisper-large-v3`, one request per episode

## Context

The extraction step needs the episode text with timestamps, and the transcript is an internal
artifact. The previous prototype proved Groq's `whisper-large-v3` on Spanish audio. Windows are
capped at 14 MB by BR-11 and BR-14, and Groq accepts up to 25 MB per file. The project runs from a
residential connection and payments are out of scope.

## Decision

- **Groq** with `whisper-large-v3`, language `es`, `verbose_json` and segment timestamps.
- **One request per episode.** No chunking: the window rules keep every file under the limit, and a
  single request keeps the offset logic trivial.
- **Offset in the step.** Each segment is stored as `start + window_start_s`, so the transcript uses
  real episode seconds.
- **Retries** of 5, 15, 45 and 90 seconds on 429, 5xx and connection or timeout errors.
- **Stop the batch on exhausted quota.** After the retries, a rate limit raises `StopBatch`: the
  step stays `pending` and the batch stops instead of failing every remaining episode.
- **Artifacts:** `data/transcripts/<video_id>.json` and `.txt`, written atomically.
- **Local fallback deferred.** `faster-whisper` is not wired in. It remains the answer if Groq's
  quota or availability becomes a real obstacle.

## Alternatives considered

- **Chunking the audio.** Unnecessary while the window cap keeps files under 25 MB; it would add
  offset bookkeeping and a second source of errors.
- **Local `faster-whisper` from the start.** No quota, but slower on CPU, heavier to install
  (`av` version constraints) and worse on proper names than `large-v3` in the prototype.
- **OpenAI's hosted Whisper.** Paid, and the project explicitly prefers free tiers.
- **Transcribing the whole episode.** Ten to twenty times more audio for the same section.

## Consequences

- Transcription depends on Groq's availability and quota. The retry and `StopBatch` behavior makes
  that visible and resumable.
- Proper names will still come out wrong sometimes; that is expected and is why the extraction
  combines the transcript with the subtitles.
- If a future episode exceeds 25 MB, the step fails with a clear message instead of silently
  truncating audio. The fix is a smaller window or chunking, not a bigger upload.
- The transcript format is stable: a JSON list of `{t, text}` plus a text rendering for review.
