# Contributing

Contributions should keep the engine explicit, typed, reproducible, and auditable. Discuss
material architecture or scope changes before implementation; significant architecture changes
require an ADR in `docs/adr/`.

## Development environment

Use Python 3.12 and uv 0.8.22. Create the locked development environment with:

```bash
uv sync --locked --extra dev --python 3.12
```

Do not update `uv.lock` incidentally. Dependency changes need a clear implementation need,
review, and corresponding lockfile update.

## Quality gates

Before submitting a change, run the checks appropriate to its scope:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
git diff --check
```

The complete suite includes platform-specific and qualified PDF checks. Report skips and
environment limitations accurately. Documentation-only changes may use focused static checks
when runtime behavior and configuration are untouched.

## Tests and fixtures

- Add focused tests for behavior changes and regression fixes.
- Every parser must use entirely synthetic fixtures.
- Use reserved domains and IP ranges and conspicuously synthetic identifiers.
- Do not copy, sanitize, pseudonymize, or derive a fixture from client or real-case material.
- Preserve source locators, provenance, and the distinction between OBSERVED, DERIVED,
  REPORTED, and HYPOTHESIS.

## Data safety

Never add real evidence, client data, case databases, generated case reports, local paths,
secrets, or operational logs to the repository. Keep originals and all case working/output
directories outside the clone. `.gitignore` is a secondary safeguard and does not replace
review of staged content and history.

Before committing, inspect at least:

```bash
git diff --check
git diff --cached
git status --short
```

## Scope discipline

Keep changes within the approved capability. Do not add external integrations, uploads,
telemetry, cloud services, new parsers, inference, or schema changes as incidental work.
Schema changes require an explicit migration and upgrade strategy. Do not describe the project
as certified forensic software or turn correlation candidates into identity, authorship,
causality, or legal conclusions.
