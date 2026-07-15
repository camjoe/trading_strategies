# Contributing

Workflow and expectations for human contributors. **AI agents** should read **[AGENTS.md](AGENTS.md)** instead (routing, conventions, shortcut workflows); this file is the human-facing companion.

## Development setup

Use the repo-local virtual environment — never system Python.

```sh
# Windows
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# POSIX
./.venv/bin/python -m pip install -r requirements-dev.txt
```

`requirements-base.txt` is runtime-only; `requirements-dev.txt` adds test/lint tooling. Run all commands from the repository root as modules (e.g. `python -m trading.interfaces.cli.main`).

## Running checks

| Command | What it runs |
|---|---|
| `python -m scripts.fix_checks` | Safe mechanical fixes: Ruff lint fixes, formatting, generated reference-doc assets, docs drift fixes |
| `python -m scripts.run_checks quick` | Repository safety checks + Python lint/type/test checks |
| `python -m scripts.run_checks ci` | Docs + repository + Python + frontend checks |
| `python -m scripts.checks.run_suite <area>` | Tests for one area, e.g. `src/trading/services/reporting` |
| `python -m scripts.run_checks python --base <base>` | Branch-targeted Python checks for PR validation |

Use `scripts.fix_checks` for normal cleanup. Lint/format directly with `ruff check .` and `ruff format .` only when you need lower-level control.

## Making a change

1. Read **[docs/architecture/architecture-conventions.md](docs/architecture/architecture-conventions.md)** before editing under `src/trading/` — respect the layering and dependency-direction rules.
2. Add or update tests; run the matching suite.
3. Update any documentation the change touches (see **[docs/README.md](docs/README.md)**; the `docs/maps/docs-map.md` "Goes stale when" column maps code → owning docs).
4. Run `python -m scripts.run_checks quick` (and `ci` before a PR).
5. Record architectural decisions as an ADR in `docs/adr/`.

The Definition of Done lives in `.ai/skills/validate-code/SKILL.md` — its "Not covered here" section lists what you must verify manually.

## Database changes

- The schema is owned by the numbered Alembic revision chain in `src/infrastructure/database/alembic/versions/`.
- Revisions are **immutable, numeric, and single-head** — never edit an applied revision; every revision implements `upgrade()` and `downgrade()`; bump `schema_version.EXPECTED_HEAD_REVISION` in the same commit. `NOT NULL` additions must supply a `DEFAULT`.
- See **[docs/reference/db-migration-system.md](docs/reference/db-migration-system.md)** and the `db-migration` skill.

## Pull requests

Run `python -m scripts.run_checks repo` and `python -m scripts.run_checks python --base <base>` first. Include in the PR:

- Summary of the change and **why**
- Testing performed
- Any documentation updates

## Please avoid

- Using system `python`/`pytest` instead of `.venv`
- Editing existing/applied migration files
- Skipping tests or the layer check
- Adding code that inverts the dependency direction (`interfaces → services → repositories/domain → database`)
