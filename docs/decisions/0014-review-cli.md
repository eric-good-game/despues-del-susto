# 0014 — Review: an interactive CLI, not an admin page

## Context

After the first catalog pass there were 29 recommendations that the matcher could not settle: 25
`needs_review`, 2 `no_match` and 2 `manual_pending`. The old documentation left the review tool
open: command line or administration page. The author is the only operator, the project runs
locally, and there is no server or authentication layer yet.

## Decision

- **Interactive CLI** (`dds review`) built with `rich`. It walks the pending cases in playlist
  order and shows the episode, titles, confidence, mention second and candidates.
- **Actions:** choose a candidate, search another title, create a manual work, discard, skip, quit.
- **States:** a resolved case becomes `manual_resolved` with `decided_by = manual`. A discarded case
  becomes `discarded`. Both keep the history.
- **Manual works** use `source = manual` and an `external_id` derived from title and year. They
  cover books and `other` works that have no automatic source.
- **Confirmed corrections** are allowed with `--all`; the previous work is removed if it becomes
  orphaned.
- **No publication approval.** `dds review status` is a workload summary; the site phase will
  define when an episode is publishable.
- **No administration page.** It would need hosting, authentication and a server-side database,
  none of which exist in the local-first version.

## Alternatives considered

- **Web admin page.** Better for remote work, but it adds the whole server stack just to edit rows
  that only one person edits.
- **Flags-only commands** (`dds review resolve --id ...`). Scriptable, but the decision needs the
  context of several candidates and the ability to search again; a prompt is a better fit.
- **Editing SQLite by hand.** Fast for one row, error-prone for the states, work creation and
  candidate flags.

## Consequences

- Review is fast for a local operator and requires no infrastructure.
- Manual decisions are protected: enrichment only processes `decided_by = automatic`.
- The interaction is harder to automate; the service functions behind the CLI are separately
  testable and can later power an admin page if the project moves to a server.
- A wrong automatic match can be corrected without re-running the whole pipeline.
