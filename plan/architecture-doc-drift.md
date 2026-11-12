# Plan: bring the architecture docs back in line with the tree, and check the ownership table

Status (2026-11-11): drafted. Nothing built. No owner decision is open for items 1-2; item 3 is optional and
waits for the owner's yes.

Keep this file until the "Left to do" list is empty.

## Left to do
Check these off in the pull request that does each one; delete this file when none remain.
1. **Item 1, correct the statements that disagree with the code** in `service-ownership.md` and
   `architecture-conventions.md`.
2. **Item 2, check the ownership table against the service packages**, so a missing or extra row fails the
   docs check.
3. **Item 3 (optional), one ownership sentence in each service package docstring.** Needs the owner's yes.

## Goal
A reader who opens `docs/architecture/` should be told the truth about where things live. Today a handful of
statements describe an older shape of the code. Fix those, then make the one table that can be checked
mechanically fail the docs check when it drifts (`docs/conventions/documentation-maintenance.md`, principle 2:
generate or check the mechanical).

Docs only, plus one check. **No source module moves and no behaviour changes.** Where the doc and the code
disagree, this plan changes the doc to match the code. If a finding looks like the code is the one that is
wrong, stop and ask instead of editing either.

## What exists (verified, 2026-11-11)
Names and quoted phrases, not line numbers.

### `docs/architecture/service-ownership.md`
- **`universe/` has two rows** in the ownership table, with different text. It is not a package: the code is
  the single module `src/trading/services/universe.py`.
- **`advisor/` and `operations/` have no row.** Both are packages under `src/trading/services/`
  (`advisor/` has six modules, `operations/` has four).
- The other fourteen packages each have one row: `accounts`, `analysis`, `auto_trading`, `autonomy_monitor`,
  `books`, `evaluation`, `execution`, `fixtures`, `market_data`, `operational_settings`, `parameters`,
  `promotion`, `reporting`, `strategy_catalog`.
- **The `books/` row and the layout sketch name three modules** (`book_assignments`, `sector_config`,
  `helpers`). The package has eight: those three plus `configuration`, `default_book`, `operations`,
  `provisioning`, and `settings_validation`. The `books/__init__.py` docstring repeats the three-module list.
- **"Presentation ownership" says the `show_*`/`render_*` entrypoint is "exposed on the package `__init__`".**
  The "Facades" section of the same file says not to add a re-export `__init__`, and every service
  `__init__.py` is a docstring only (the longest is 11 lines).

### `docs/architecture/architecture-conventions.md`
- **"Detail the one-line rules do not carry" says models live "in feature subfolders (`accounts/`, `books/`, …),
  one contract per file".** `src/trading/models/` is flat feature modules (`accounts.py`, `books.py`, …) that
  each hold many contracts. ADR 005 and a later paragraph of the same file (the `backtesting/` bullets) both
  describe grouped feature modules as the intended shape.
- **The Package Ownership Map says `trading/models/` "imports nothing from any other layer".** Four model
  modules (`accounts.py`, `books.py`, `orders.py`, `portfolio.py`) import
  `trading.persistence.money_columns`. That is allowed: "Allowed" rule 4 lets any layer import
  `trading/persistence/`, and the `layer_check` rule for models forbids `domain`, `services`, `repositories`,
  `interfaces`, `backtesting`, and `infrastructure` only. The one-line rule and
  `docs/maps/trading-package-map.md` ("imports nothing from other trading layers") leave the exception out.
- **"Import and Facade Rules" rule 1 says to import the owning module, "not a package-root re-export".**
  `trading/models/__init__.py` re-exports 24 names on purpose (ADR 005: "The package root re-exports the stable
  public types"), and `from trading.models import ...` appears 39 times in `src/` and `apps/`. The rule does
  not mention that exception.

### Tooling
- `scripts/checks/docs/maps_check.py` compares the map tables under `docs/maps/` with the files on disk.
  Nothing checks `service-ownership.md`.
- **Unverified:** whether `scripts/checks/` or the docs check wiring is on the guarded-path list
  (`scripts/forge/guarded_paths.py`). Read it before item 2; a guarded path cannot be changed by the unattended
  pickup.
- **Unverified:** whether the in-app documentation content (`scripts/documentation_ui/`) copies any of the
  sentences above. Search it and keep the two in step.

## Work items
Item 1 is one pull request. Item 2 is a second. Item 3, if approved, is a third.

### 1. Correct the statements
In `service-ownership.md`:
- Merge the two `universe/` rows into one, titled `universe.py`, keeping the more specific text ("expands
  universe names into ticker lists for the write paths; owns the default-universe vocabulary", and that nothing
  in it runs on the trading path).
- Add a row for `advisor/` and one for `operations/`. Write each from the module docstrings and the rows
  already in `docs/maps/trading-package-map.md` (it has a row per module for both). State what the package does
  **not** own only where the code makes that clear; otherwise use the same dash the other rows use. Do not
  invent a boundary.
- Rewrite the `books/` row and the layout sketch to cover all eight modules, grouped by what they do, and fix
  the matching sentence in the `books/__init__.py` docstring.
- In "Presentation ownership", replace "exposed on the package `__init__`" with what the code does: callers
  import the entrypoint from the package's `presentation.py`.

In `architecture-conventions.md`:
- Replace the "feature subfolders … one contract per file" clause with the real arrangement: feature modules
  (`accounts.py`, `books.py`, …), one coherent area per module.
- In the Package Ownership Map row for `trading/models/`, state the rule as enforced: nothing from `domain`,
  `services`, `repositories`, `interfaces`, or `infrastructure`; `trading/persistence/` and `common/` are
  allowed. Make the same correction to the one-line description in `docs/maps/trading-package-map.md`.
- In "Import and Facade Rules" rule 1, add the standing exception in one sentence: the `trading.models` (and
  `backtesting.models`) roots re-export their stable public types by decision (ADR 005). **Unverified:** that
  `backtesting/models/__init__.py` re-exports the same way; the conventions file says it does ("feature modules
  with a re-exporting root"), confirm in the code before writing it.
- Bump `Last Reviewed` on each file touched.

While in these two files, read them once end to end against the tree and fix any other statement of fact that
is wrong. List each one in the pull request. Do not rewrite for style, and do not change a rule: a sentence
that says what must be done is a decision, and only its description of the current code is in scope.

### 2. Check the ownership table
- Add a docs check that reads the first column of the ownership table in `service-ownership.md` and compares it
  with the packages and top-level modules in `src/trading/services/` (skip `__init__.py` and `__pycache__`).
  It reports a package with no row, a row with no package, and a duplicated row.
- Put it where the existing docs checks live and wire it into the same profiles as `maps_check`, with the same
  advisory and enforce behaviour. Prefer extending `maps_check.py` if its table parsing can be reused without
  bending it; otherwise a small sibling module. Say which in the summary.
- Tests in `tests/scripts/`, following `test_maps_check.py`: a table that matches, a missing row, an extra row,
  a duplicate.
- Add the check to `docs/maps/scripts-map.md`.
- It must pass on the tree as item 1 leaves it. Do item 1 first.

### 3. Ownership sentence in each package docstring (optional, held for the owner)
Thirteen of the sixteen service `__init__.py` files are three lines long; `accounts/__init__.py` reads
"Accounts service package." **Unverified:** that the other twelve say as little; read each before rewriting it.

- Give each package docstring two short lines: what the package owns, and the one or two things most often
  mistaken for its job with where they live instead. Take the wording from the ownership table.
- This duplicates the table on purpose, so a reader in the editor sees it without opening `docs/`. That is a
  new duplication seam (`documentation-maintenance.md`, principle 3). Only do it if the item 2 check is
  extended to fail when a package has no such docstring; do not add prose that nothing checks.

## Constraints
- Follow `docs/conventions/docs-authoring.md` for headers and layout, and
  `.ai/skills/update-documentation/SKILL.md` for the drift workflow.
- Item 1 touches `src/` only for the `books/__init__.py` docstring. Read
  `docs/architecture/architecture-conventions.md` in full first all the same.
- `AGENTS.md` is not edited by this plan. Its skills table and routing guide were not audited.
- Nothing here is strategy-specific; all of it is intentionally public.
- Run `python -m scripts.run_checks docs --advisory` before and after, then `python -m scripts.fix_checks` and
  `python -m scripts.run_checks pr --base origin/develop`.
- **Environment (seen 2026-11-11 on the dev PC):** the `.venv` editable install resolved to a different
  checkout, so `pytest` failed on import until `PYTHONPATH` pointed at this checkout's `src` and `apps`. If
  imports fail the same way, report it; do not reinstall the environment unasked.

## Decisions needed (owner)
- Item 3: whether to add the ownership sentences to the package docstrings.

## Out of scope
- Moving `services/universe.py` into a package, or any other source move.
- The two import cycles between service packages (`accounts` and `books`, `books` and `evaluation`) and a
  dependency-direction rule for services. That is a code change with its own plan.
- Auditing `docs/reference/`, `docs/runbooks/`, the ADRs, or `nav-guide.md` and `service-cookbook.md`. Only the
  two architecture files above were compared with the code.
- Shortening or merging docs.

## Developer verification (fill in when the work ships)
- Item 1: the ownership table has seventeen rows, one per entry in `src/trading/services/` (sixteen packages
  and `universe.py`); `git grep -n "one contract per file" docs` returns nothing.
- Item 2: deleting a row from the table makes `python -m scripts.run_checks docs --advisory` report it.
- Item 3: to be filled in.
