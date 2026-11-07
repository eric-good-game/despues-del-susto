# 0008 — Progress output for long commands

> Status: **proposed, not implemented**. Written down so the design is not lost; it is implemented
> when a phase makes the silence painful again.

## Context

`dds ingest --all` and `dds sync` buffer their work and print only when they finish. A batch over
50 episodes, or a first sync that fetches 50 metadata entries, produces several minutes of silence.
There is no way to tell whether the process is working, stuck on the network or waiting on a rate
limit.

## Proposed design

- Services do not print. They emit progress events: episode started, step started, step finished,
  metadata fetched `N/M`.
- The CLI renders those events. Output goes to **stderr**, so the final report on stdout stays
  clean and can be redirected.
- Default rendering is plain lines, flushed immediately:

  ```
  [ 3/50] 0I7ueTFcMb8  Episode title
           subs       done    1.4s
           anchor     done    0.02s  ok (intro,juego,peli) 1508s
           audio      done    9.7s   window 1418s (anchor)
  ```

- `--quiet` keeps only the final report.
- A rich progress bar can later be layered on the same events. It is not part of this proposal
  because it hides history and behaves differently when output is redirected.
- An optional file log under `data/logs/` can be attached later through a logging handler.

## Why it is not implemented yet

The commands finish quickly at the current stage, and adding an event layer now would touch the
orchestrator while its steps are still being built. Revisit when phase 5 or 6 makes a batch run
long enough to justify it.

## Consequences when implemented

- The orchestrator gains a callback; tests keep asserting behavior, not formatting.
- Progress lines are stable enough for scripts but explicitly not part of the published data.
- Redirecting stdout to a file no longer hides the running state.
