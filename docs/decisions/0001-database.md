# 0001 — Local database: SQLite with SQLAlchemy and Alembic

## Context

Version 1 runs on the author's machine and needs to persist episodes and the state of each
pipeline step. The schema will grow with every phase (works, recommendations, availability), and
a half-processed episode must survive between runs.

## Decision

- **SQLite**, in a single file at `data/dds.db`.
- **SQLAlchemy 2.0** with typed ORM models, instead of hand-written SQL.
- **Alembic** for migrations, with the migration scripts shipped inside the package.
- Every command brings the schema up to date before touching data (`ensure_schema`), and
  `dds db upgrade` does it explicitly.

## Consequences

- One file to back up, one writer at a time. Enough for a single-user local tool.
- The schema can change without losing processed episodes; every change needs a migration.
- SQLite's limited `ALTER TABLE` is covered by Alembic's batch mode.
- The database is local by design. Publishing to a server is a later phase and will not reuse
  this file directly.
