# 0007 — Anchor detection: port the patterns, measure before tuning

## Context

The audio download must cover only the recommendations section, normally at the end of each
episode. The prototype found it by searching the subtitles for fixed phrases and restricting
matches to the second half of the episode and to the last 12 minutes. The approach worked on the
50 available episodes; 13 were only partially detected.

## Decision

- **Port the prototype patterns**, grouped by kind: `intro`, `juego`, `peli`. They live in
  `steps/anchor.py` and are the starting point, not a permanent truth.
- **Drop rolling-caption prefixes before matching.** Auto subtitles repeat a line as it grows; the
  prototype searched duplicated text. Removing prefixes reduces noise and makes offsets map to the
  real line.
- **Keep the two position rules** as parameters in `rules.md`: second half, at most 720 s from the
  end.
- **Earliest kind wins.** The anchor is the earliest valid match among the kinds; all detected
  kinds are stored.
- **Store the evidence.** The fragment that triggered the detection is saved internally so a
  doubtful case can be reviewed without re-running the pipeline.

## Alternatives considered

- **Let the LLM find the section in the subtitles.** It would replace a deterministic, testable
  step with a probabilistic one, and the section is only needed to bound audio. Deferred.
- **Search the transcript instead of the subtitles.** The transcript does not exist yet, and the
  subtitles are available before any audio download.
- **Use fixed percentages of the episode.** Ignores where the section actually starts and wastes
  audio.

## Consequences

- The patterns are text, not semantics: they can miss new ways of introducing the section. The
  `parcial` and `sin_ancla` states surface that instead of failing silently.
- Thresholds are initial values. After the first run over 50 episodes, the distribution is
  measured and `BR-01`/`BR-02` are adjusted before tuning the audio margins.
- A wrong anchor only affects how much audio is transcribed; it does not corrupt the catalog, and
  `--redo anchor` re-runs the step and everything after it.
