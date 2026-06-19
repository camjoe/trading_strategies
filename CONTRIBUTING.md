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
| `python -m scripts.run_checks --profile quick` | Layer check + ruff + targeted tests |
| `python -m scripts.run_checks --profile ci` | Full suite + mypy + frontend |
| `python -m scripts.checks.run_suite <area>` | Tests for one area, e.g. `trading/services/reporting` |
| `python -m scripts.checks.pr_ready --base <base>` | Full deterministic pre-PR gate |

Lint/format directly with `ruff check .` and `ruff format .`.

## Making a change

1. Read **[docs/architecture/architecture-conventions.md](docs/architecture/architecture-conventions.md)** before editing under `trading/` — respect the layering and dependency-direction rules.
2. Add or update tests; run the matching suite.
3. Update any documentation the change touches (see **[docs/README.md](docs/README.md)**; the `docs/maps/docs-map.md` "Goes stale when" column maps code → owning docs).
4. Run `python -m scripts.run_checks --profile quick` (and `ci` before a PR).
5. Record architectural decisions as an ADR in `docs/adr/`.

The Definition of Done lives in `bots/skills/validate-code/SKILL.md` — its "Not covered here" section lists what you must verify manually.

## Database changes

- Schema lives in `trading/database/db_schema.py`; migrations in `trading/database/db_migrations.py`.
- Migrations are **append-only `ColumnMigration` entries** — never drop or rename a column, never edit an applied migration. `NOT NULL` additions must supply a `DEFAULT`.
- See **[docs/reference/db-migration-system.md](docs/reference/db-migration-system.md)** and the `db-migration` skill.

## Pull requests

Run `python -m scripts.checks.pr_ready --base <base>` first. Include in the PR:

- Summary of the change and **why**
- Testing performed
- Any documentation updates

## Please avoid

- Using system `python`/`pytest` instead of `.venv`
- Editing existing/applied migration files
- Skipping tests or the layer check
- Adding code that inverts the dependency direction (`interfaces → services → repositories/domain → database`)
