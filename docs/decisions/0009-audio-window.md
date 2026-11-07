# 0009 — Audio window: conservative margins, 48 kbps MP3, accurate cuts

## Context

Transcribing a full episode is slow, expensive and mostly useless: the recommendations are at the
end. The window must be small enough to stay under transcription limits but generous enough not to
cut off the start of the section. The audio is an internal artifact and is never published.

## Decision

- **Window rules** (`BR-09` to `BR-13`): 90 s of margin with an `ok` anchor, 240 s with a
  `parcial` anchor, 420 s when that anchor is also close to the end, and the last 45 % (capped at
  1500 s) when there is no anchor. The window always reaches the end of the episode.
- **MP3 at 48 kbps** (`DDS_AUDIO_QUALITY`). At 128 kbps a 40-minute window would exceed the 25 MB
  limit of the transcription service; 48 kbps leaves even the expanded window around 14 MB.
- **Accurate cuts** with `--force-keyframes-at-cuts`. Without it the audio can start seconds away
  from the requested second, and the offset applied to the transcript would be wrong.
- **The offset lives in the database** (`episode_processing.window_start_s`), not in a CSV. The
  database is the source of truth for the pipeline state.
- **The step does not fetch metadata.** Missing duration or anchor data fails with a message;
  `dds sync` is the command that fills metadata.
- **The expanded window** (last 60 %, capped at 2400 s) is computed and recorded with origin
  `expanded`, but the extraction step decides when to use it in phase 6.

## Alternatives considered

- **Download the whole episode.** Simpler, but 10 to 20 times more audio to transcribe and store,
  and more room to hit size and time limits.
- **Cut with a separate `ffmpeg` command.** yt-dlp already does it, and adding a second tool would
  duplicate offset bookkeeping.
- **Higher bitrate for quality.** Unnecessary: speech recognition works well at 48 kbps, and the
  size limit is a hard constraint.
- **Compute the window in the transcription step.** It belongs to the audio step: the file that is
  downloaded is defined by the window, and storing the offset next to the artifact keeps them
  consistent.

## Consequences

- Windows are deliberately conservative. If the section starts earlier than expected, the extra
  audio is cheap; if it starts later, the margin absorbs it.
- Re-downloading is required when the anchor changes; `--redo audio` already invalidates the steps
  that depend on it.
- Reducing the bitrate or the margins is a parameter change, not a code change, as long as the
  limits hold.
