# 0008 — Progress output for long commands

> Status: **implemented in phase 5a**. The rich progress bar and the file log were not included.

## Context

`dds ingest --all` and `dds sync` used to buffer their work and print only when they finished. A
batch over 50 episodes, or a first sync that fetches 50 metadata entries, produced several minutes
of silence. There was no way to tell whether the process was working, stuck on the network or
waiting on a rate limit.

## Decision

- Services do not print. They emit events through a `ProgressSink`: episode started, step started,
  step finished, episode finished, metadata started, metadata failed.
- The CLI renders them with `ConsoleProgress`, using plain lines flushed immediately.
- **Streams:**
  - A single-episode `ingest` writes the step lines to **stdout**, because they are the result.
  - A batch and `sync` write progress to **stderr**, keeping stdout for the final report.
  - The final report always goes to stdout.
- `--quiet` suppresses progress. A single-episode summary still prints; in a batch only the final
  `Batch: …` line prints.
- Step lines include the elapsed time, and a `running` line before the step starts so a long
  download or transcription is visible while it happens.

Example:

```
[ 1/2] ep1  Episodio 1
  subs: running
  subs: done (0.0s)
  anchor: done (0.0s)
  audio: running
  audio: done (9.7s)
  transcribe: running
  transcribe: done (41.2s)
ep1: done 4, skipped 0, stopped at extract
```

## Alternatives considered

- **Rich progress bar.** Nicer in a terminal, but it hides the history and behaves differently when
  output is redirected. The event layer leaves the door open to add it later.
- **Logging only.** A file log is useful for auditing, but it does not show what is happening right
  now unless the user tails it. Deferred.
- **Printing from the services.** Simple, but it couples the domain to the terminal and makes the
  output untestable.

## Consequences

- The orchestrator measures elapsed time per step and emits events; tests assert behavior, not
  formatting.
- Redirecting stdout to a file no longer hides the running state of a batch.
- The format is stable enough for scripts, but it is not part of the published data.
