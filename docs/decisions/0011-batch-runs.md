# 0011 — Batch runs select by pending step, not by offset

## Context

Processing the 50 episodes at once is inconvenient: transcription consumes a limited API quota, and
a long silent run is hard to follow. The obvious flag, `--limit N`, has a trap: after processing the
first N episodes, the next run would pick the same N again. At any phase, the steps after the last
implemented one are pending for every episode, so "episode complete" is never true.

## Decision

- `--all` selects episodes where the **last implemented step** is not `done`, in playlist order.
  `--limit N` caps that selection.
- The target step is derived from the step registry, not configured by hand. When a phase implements
  the next step, the target moves automatically.
- `--redo <step>` makes every episode eligible, because a redo is an explicit request to revisit
  finished work.
- A batch stops immediately when a step raises `StopBatch`. The step is left `pending`, not
  `failed`, and the remaining episodes are untouched. The first use is an exhausted transcription
  quota.
- The final report states processed, failed and remaining counts for the target step.

## Alternatives considered

- **Offsets or ranges by position.** Easy to implement, but they break when the playlist is
  reordered or grows, and they do not know which work is actually missing.
- **Process all episodes every run.** Wasteful, and it burns quota on finished episodes.
- **Wait until all steps are implemented.** Postpones the useful case: batching exists precisely
  because transcription is limited.

## Consequences

- Re-running the same command always makes progress; no manual bookkeeping.
- A step that fails stays pending and is retried first on the next run. A permanently broken
  episode can block the head of the queue; that is visible in the status table and can be handled
  with `--redo` or by fixing the cause.
- The batch's meaning changes with each phase, which is intended: the command is "advance the
  catalog through the last implemented step", not "run these exact steps".
