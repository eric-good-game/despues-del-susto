# 0003 — Local artifact layout

## Context

Some steps produce large files (subtitles, audio, transcripts). Keeping them in the database
would bloat it; keeping their existence only on disk would make runs impossible to resume
reliably. The two need a clear split.

## Decision

```
data/
  dds.db                              # state and entities
  subs/<video_id>.<lang>.json3        # subtitles
  audio/<video_id>.mp3                # audio window
  transcripts/<video_id>.json         # transcript with seconds
  extractions/<video_id>.json         # raw model output
  cache/<provider>/                   # cached provider responses
```

- **The database is the source of truth for state.** Whether a step ran, and whether it succeeded,
  lives in `processing_steps`, never in the presence of a file.
- **Artifacts are regenerable.** Deleting one does not corrupt the database; it only means the
  corresponding step must run again.
- **One file per episode and step.** The `video_id` is always in the filename, so files can be
  found without the database and inspected by hand.
- **Metadata that later steps need** (window start, anchor second) goes into the database, not into
  sidecar CSV files. The prototype used `offsets.csv`; that pattern is retired.
- **Enrichment lives in the database.** Works and candidates are rows, not an `enriched/` file; the
  provider responses are cached under `data/cache/` for debugging and reuse.
- **Nothing under `data/` is versioned.**

## Consequences

- Resuming works even if an artifact is missing only when its step is marked as not done; the
  pipeline must not trust a file without checking state.
- Backups need both the database and `data/` to avoid re-downloading audio.
- Prices and other data that may not be stored, per source terms, never enter either.
