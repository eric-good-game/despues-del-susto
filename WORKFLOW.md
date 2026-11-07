# Workflow

How this project is built. Short on purpose: it covers the rules that are expensive to change
later, not the shape of the product.

## Principles

1. **Just in time.** Documentation is written when the code that needs it is written. No upfront
   specification of features that are not being built yet.
2. **Walking skeleton first.** A capability is wired end to end before it is deepened, so the
   plumbing (CLI, config, database, logging, tests) is proven with stubs.
3. **Small vertical slices.** One slice delivers something observable, from input to output.
4. **Docs follow code.** If a change alters behavior or terminology, the document changes in the
   same pull request.

## Branching

Trunk-based: `main` is always green.

- Short-lived branches: `feat/...`, `fix/...`, `docs/...`, `chore/...`.
- Merge within a day or two. No long-running branches.

## Commits

Conventional Commits. Subject in English, imperative; body in Spanish when it helps explain why.

```
feat(anchor): detect the recommendations section
fix(audio): keep the window from starting before zero

Se descarta el margen cuando el ancla está antes de ese segundo.
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`.

## Pull requests

Even when working alone, open a PR for anything beyond a trivial change. It is where the reasoning
is recorded. The body answers:

- What changes.
- Why.
- How it was verified.

Squash merge. The PR title follows the commit format.

## Definition of done

A slice is done when:

- [ ] It does what the corresponding `BR`/`UC` describes, or that rule was updated.
- [ ] Tests cover the new behavior, or the PR explains why there are none.
- [ ] `ruff check` and `pytest` pass.
- [ ] Documentation is updated if behavior or terminology changed.
- [ ] Committed with a conventional message.

## Documentation

- Lives in `docs/`, written in English.
- Product docs are created only when a phase needs them: glossary, business rules, data model,
  architecture.
- Non-trivial technical decisions get a short record in `docs/decisions/NNNN-slug.md` at the moment
  they are taken. Format: context, decision, consequences.

## Language and naming

| Where | Language |
|---|---|
| Documentation, code, identifiers, table and column names, enum values, commit subjects | English |
| Copy shown to site visitors | Spanish |

- Business rules: `BR-01`, `BR-02`…
- Use cases: `UC-01`, `UC-02`…
- Data values are English: `videogame`, `movie`, `series`, `book`, `other`. Spanish translation
  belongs to the presentation layer only.

## Tooling

- Python 3.12.
- `ruff` for linting and formatting.
- `pytest` for tests.
