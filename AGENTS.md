# Trading Strategies Workspace Guide

Purpose: define the repo-level guidance, routing rules, and shortcut workflows for coding agents working in this repository.

## Core rules

- Before editing any file under `src/trading/`, read `docs/architecture/architecture-conventions.md` in full.
- Respect the layering and ownership rules there. Do not invert dependency direction such as `interfaces -> services -> repositories/domain -> database`.
- If a requested change would violate those conventions, stop and flag it before proceeding.
- Before adding a strategy primitive, feature provider, strategy-specific parameter set, fixture, or
  strategy documentation, classify it as intentionally public or private/proprietary. Only
  intentionally public examples belong in tracked files. Keep private research and parameters under
  `local/strategies/`; private executable strategy logic belongs in a separately distributed private
  package or repository behind the established strategy interfaces. When classification is unclear,
  stop and ask before writing tracked files.

## Standing authorizations

Granted by the owner on 2026-10-09, except the workflow bullet and the fixer-loop bullet, granted on
2026-10-10. Each covers only what is written here; anything else needs the owner's yes in that
conversation.

- `pr ready` may create and edit the single readiness comment on the current branch's own pull
  request, identified by the hidden marker `<!-- pr-readiness -->`, without asking. It may not post
  any other comment or review, add labels, or merge. It never posts security-class findings (route
  those to `/security-review` and tell the owner privately). The repository is public: the comment
  carries no credentials, broker account ids, local machine paths, or private strategy parameters.
- The `PR readiness` workflow (`.github/workflows/pr-readiness.yml`) may create and edit that same
  readiness comment, identified by the same hidden marker, on any non-draft pull request into
  `develop`, posting as `github-actions[bot]`, without asking. It has the same limits as `pr ready`
  above: no other comment or review, no labels, no merge, no security-class findings, and nothing
  that is not safe on a public repository. It posts only through `python -m scripts.forge
  comment-upsert`, which refuses a body that lacks the marker, and the agent step holds no GitHub
  token: a separate job, which never checks out the pull request and runs the `scripts.forge` tool from
  the base branch, checks the body the agent wrote and posts it. Changing the workflow, the forge write path, or this section needs the owner's yes.
- `python -m scripts.forge fix-loop`, started by the owner on a pull request, or by the owner's
  `implement-plan` run on the pull request it opened, may for up to three rounds
  commit to that pull request's own branch, push that branch, add `Fix attempted`, `Not fixed`, and `Left`
  lines to its readiness comment, and email the owner the pull request link, the verdict, and the open
  counts, without asking. When the comment says READY and `implement-plan` claimed a plan for the branch,
  it also commits the removal of that plan file and its index row. It never changes a
  path in `scripts/forge/guarded_paths.py` (a round that does is undone; the pickup's commits that do are
  held locally and never pushed), writes a `Decision` line, ticks a box,
  edits a finding, force-pushes, touches another branch, opens or marks ready a pull request, labels, or
  merges. The agent it starts works in a throwaway clone of the repository with its own virtual
  environment and no usable remote, and only commits that pass the loop's path check and comment-body
  check ever reach the owner's checkout, which then posts and pushes. That isolates the repository, not
  the machine: the agent still runs as the owner, with GitHub tokens and the owner's git and `gh`
  configuration withheld and tool permissions that deny pushing, resetting, and `gh`, but code it writes
  and runs can reach the rest of the filesystem and the network. `implement-plan --container` moves the
  gate, not the agent, into a container. It has the same public-repository limits
  as `pr ready`. Starting it on a schedule or from a trigger, or changing the loop, the guarded-path
  list, or this section, needs the owner's yes.

## Python environment

- Always run Python tools from the repo-local `.venv` virtual environment.
- Use the platform-appropriate interpreter and tool paths:
  - Windows: `.venv\Scripts\python.exe`, `.venv\Scripts\pytest.exe`, `.venv\Scripts\pip.exe`
  - POSIX: `./.venv/bin/python`, `./.venv/bin/pytest`, `./.venv/bin/pip`
- If a command example elsewhere in the repo uses a POSIX `.venv/bin/...` path, Windows agents should use the equivalent `.venv\Scripts\...` executable.
- Do not use system `python`, `python3`, or `pytest`.
- If `./.venv` is missing, stop and ask before proceeding.

## Working references

- Architecture boundaries: `docs/architecture/architecture-conventions.md`
- Plans for work about to start (possibly on another branch): `plan/` — short-lived, deleted when the work ships; see `plan/README.md`
- Style guides: `docs/conventions/general-style.md` (cross-cutting approach + docs/markdown), `docs/conventions/python-style.md` (Python), `docs/conventions/frontend-style.md` (TypeScript/frontend)
- Skill authoring and localization guidance: `.ai/skills/README.md` (Authoring rules)
- Supplemental Copilot-specific guidance: `.github/copilot-instructions.md`
  - `AGENTS.md` is the source of truth for durable repo instructions.
  - Read `.github/copilot-instructions.md` after `AGENTS.md` when Copilot/tool-specific legacy context is needed.
- For a readable current DB schema view, run `python -m scripts.data_ops.describe_db_schema` or `python -m scripts.data_ops.describe_db_schema --source live` instead of relying on a hand-maintained schema markdown mirror.
- Grouping several DB writes into one atomic transaction (commit once, roll back on any failure): use `unit_of_work` / `commit_unit_of_work` from `src/trading/persistence/unit_of_work.py` — see `docs/reference/database-transactions.md`.
- Writing a timestamp to a database column: render it with `utc_now_iso` / `as_utc_iso` / `normalize_utc_iso` from `src/common/time.py`, never a bare `datetime.isoformat()`. Stored timestamps are string-compared in SQL, so mixed spellings of one instant break ordering and range filters — see `docs/conventions/python-style.md` (Timestamps).

## Output style

- Apply a **balanced** style (see `docs/conventions/general-style.md`): prefer a touched file's existing local style, make consistency improvements only when they reduce ambiguity, and avoid broad style-only churn. Keep behavior unchanged unless asked.
- Do **not** do style-only rewrites unless explicitly requested.
- **Do not narrate in source.** Comments and docstrings carry facts a reader would otherwise get
  wrong — not your reasoning. Rationale for a change (what you considered, what it replaced, what
  bug it fixed, why the old way was worse) goes in the commit message and your summary, never in
  the file: code gets edited and the story rots, while `git log` stays accurate. If a change adds
  more prose lines than code lines, cut it back. Full rule: `docs/conventions/python-style.md`
  (Comments and docstrings).
- Explain any non-trivial style decision in your summary.
- For new code, apply the relevant language guide by default — `docs/conventions/python-style.md` (Python), `docs/conventions/frontend-style.md` (TypeScript/frontend).
- After each completed implementation phase and in final summaries, include:
  - `Developer verification`: exact UI route/tab/control, API endpoint and expected payload, report path, command output, or behavioral expectation a developer can inspect.
  - `Validation run`: tests and checks executed, or why validation was not run.
  - `Cleanup/robustness notes`: obsolete code removed, evidence-based cleanup candidates found in the touched scope, or `none found in touched scope`.
- Cleanup reporting is advisory by default. Do not broaden a feature branch with unrelated removals unless the obsolete path is directly created or exposed by the current change and validation proves removal is safe.

## Task surfaces

Skills are the repository's single task surface. (Repo-specific `.agent.md` personas were retired
2026-07-02 — their unique safety content moved into skills and `docs/architecture/architecture-conventions.md`.)

### Skills

Use a skill whenever the task matches one.

**Skills layout:** Canonical definitions live in folder-based files (`.ai/skills/<skill-name>/SKILL.md`). Reference files (mode-specific or domain-specific detail) live as flat `.md` files inside the same skill folder and are loaded on demand.

Do not reintroduce retired flat `.skill.md` shims, blank skill templates, or retired standalone skills without a fresh decision.

Current skill inventory:

| Skill | Purpose |
|---|---|
| `check-pr-readiness/` | Full pre-PR workflow: the gate, independent reviewers chosen by the diff, a docs drift review, and one readiness comment on the PR |
| `fix-pr-readiness/` | Resolve a readiness comment's findings that need no decision: one commit each, every attempt recorded on the comment |
| `implement-plan/` | Implement one plan from `plan/` on its own branch: commits with tests, questions instead of guesses, nothing pushed by the agent |
| `code-review/` | All review modes: standard, baseline, aggressive, architecture, cleanup, contract, PR review, and the independent lens reviewers |
| `create-runtime-job/` | Scaffold a new runtime job against the shared runner (module + test + sentinel + schedule + inventory) |
| `db-migration/` | Schema migration lifecycle: create, validate, estimate risk, generate rollback |
| `finance-strategy/` | Financial terminology, strategy classification, market mechanics, and evaluation honesty |
| `strategy-advisor/` | Advisor session: score past decisions, read the digest, record a decision per book (including hold), act only on approval |
| `update-documentation/` | Docs drift sync — rewrite stale prose, descriptions, and responsibilities |
| `validate-code/` | Deterministic validation: repo checks + Python lint/type/test checks |

## Routing guide

Default to the most specific matching skill; work without one when nothing matches.

| Task shape | Preferred surface |
|---|---|
| Architecture, layering, dependency direction | `code-review/` (Architecture mode) |
| Pre-commit or pre-merge audit | `code-review/` (Standard mode) |
| Lightweight quick diff check | `code-review/` (Baseline mode) |
| High-risk or safety-critical review (broker, DB, admin) | `code-review/` (Aggressive mode) |
| Whole-area simplification or stale-code audit | `code-review/` (Cleanup mode) |
| Create or update a reference doc or ADR | Follow `docs/conventions/docs-authoring.md` |
| README, reference, or API drift | `update-documentation/` |
| Frontend-only cleanup in `apps/paper_trading_web/frontend` | `code-review/` (Cleanup mode) |
| Generic Python cleanup or refactor | `code-review/` (Cleanup mode) |
| Mixed backend and frontend cleanup | `code-review/` (Cleanup mode) |
| Financial concept or strategy explanation | `finance-strategy/` |
| Cross-stack route/schema/UI contract work | `code-review/` (Contract mode) |
| Pre-PR readiness check (any scope) | `check-pr-readiness/` |
| Fix the findings in a PR's readiness comment | `fix-pr-readiness/` |
| Implement a plan from `plan/` | `implement-plan/` |
| Independent review of a PR or another branch, read by ref | `code-review/` (Lenses, `lenses.md`) |
| Run deterministic checks (repo, lint, type, tests) | `validate-code/` |
| Add or scaffold a new runtime job | `create-runtime-job/` |
| Schema migration work or safety review | `db-migration/` |
| Broker adapters or live-trading safety review | `code-review/` (Aggressive mode) + the Live Trading Safety Guard in `docs/architecture/architecture-conventions.md` |
| Runtime job / scheduler work | `create-runtime-job/` for new jobs; `docs/reference/runtime-jobs.md` + `docs/runbooks/` for operating existing ones |
| Backtest methodology, walk-forward, evaluation honesty | `finance-strategy/` (Evaluation honesty) + `docs/reference/backtesting.md` |
| Run the advisor, review strategy performance, decide what to change | `strategy-advisor/` |

## Shortcut workflows

These phrases are repo conventions for common tasks.

### `select skill:` (alias: `select bot:`)

- Treat this as a routing request before normal execution.
- Parse the text after the prefix as the task description.
- Return:
  1. recommended skill name (or "no skill — plain session")
  2. one-sentence reason
  3. whether to proceed with that surface now
- If no task text is provided, ask a short follow-up question.

### `code review`

- `code review`: review staged and unstaged changes against `HEAD`
- `code review: <branch>`: review the diff between the current branch and the given base branch
- `code review: <file-or-folder>`: review a specific area
- Follow `.ai/skills/code-review/SKILL.md` (Standard mode).

### `deep code review`

- `deep code review`: review `src/trading/` and `apps/paper_trading_web/` together
- `deep code review: trading`: review `src/trading/`
- `deep code review: paper_trading_web`: review `apps/paper_trading_web/`
- `deep code review: <file-or-folder>`: review a specific area with the same deep audit workflow
- Follow `.ai/skills/code-review/SKILL.md` (Aggressive mode).

### `sync docs` or `docs sync`

- Detect drift: `python -m scripts.run_checks docs --advisory` (README structure, links, maps, headers).
- Rewrite the flagged prose: follow `.ai/skills/update-documentation/SKILL.md`.
- After edits, re-run `python -m scripts.run_checks docs --advisory` to confirm.

### `run suite`

Run a focused subset of tests by suite name or individual file path.

- `run suite src/trading/services` — run all trading services tests
- `run suite src/trading/services/market_data` — run tests for one service
- `run suite src/trading/services/market_data src/trading/services/promotion` — combine suites
- `run suite src/trading/services/market_data/test_features.py` — target a single file
- `run suite all` — run the full test suite
- `run suite --changed` — auto-detect suites from uncommitted changes
- `run suite --base main` — auto-detect suites from changes vs a branch (PR workflow)
- `run suite --list` — show all available suite names

**Suite names mirror the `tests/` directory tree** — the suite for a source area is its
source path (e.g. changed `src/trading/services/promotion/` → `run suite
src/trading/services/promotion`; changed `apps/paper_trading_web/backend/` →
`run suite apps/paper_trading_web`). Discover all valid names with `run suite --list`.
After editing files under a source area, run its matching suite before committing —
or use `run suite --changed` to auto-detect.

Command: `python -m scripts.checks.run_suite <suite> [extra pytest flags]`

Pass `--no-cov` for fast iteration without coverage overhead.

### `run checks`

- Run `python -m scripts.run_checks quick`.
- Report pass/fail by step and include failing command details.

### `fix checks`

- Run `python -m scripts.fix_checks`.
- Use this only for deterministic, behavior-preserving cleanup such as Ruff safe fixes, formatting, generated reference-doc asset sync, and docs drift fixes (DB schema Quick Reference sync, stale map row removal — see `scripts/fixes/`).
- Docs drift fixes may leave `TODO` scaffold rows (e.g. a new table's Purpose); fill those in before committing.
- Afterward, run `python -m scripts.run_checks quick` unless the user asked only for the fixer.

### `run all checks`

- Run `python -m scripts.run_checks ci`.
- Report pass/fail by step and include failing command details.

### `pr ready`

Full pre-PR readiness workflow, run on committed work. Follow `.ai/skills/check-pr-readiness/SKILL.md`
— it owns the step order, stop conditions, and the readiness comment on the pull request (updated in
place by each pass; with no PR yet the text is printed).

- `pr ready` — vs `develop` (default base)
- `pr ready: <base>` — vs a custom base branch (e.g. `pr ready: main`)
- `pr ready: lenses=<names>` — override the reviewers `review_scope_check` suggests

**Individual step shortcuts** — run any step on its own:

| Shortcut | What it does |
|---|---|
| `pr gate` | The gate: enforced docs checks, repo checks, branch-targeted Python checks, and frontend checks if the diff touches the frontend (`python -m scripts.run_checks pr --base develop`) |
| `pr gate: <base>` | The gate vs a custom base |
| `pr tests` | Branch-targeted Python checks only (`--base develop`) |
| `pr tests: <base>` | Branch-targeted tests vs a custom base |
| `pr lint` | Repository checks + Python lint/type checks |
| `pr arch review` | The Architecture and conventions reviewer for the branch diff vs develop |
| `pr arch review: <base>` | The Architecture and conventions reviewer vs a custom base |
| `pr code review` | The lens reviewers `review_scope_check` selects for the branch diff vs develop |
| `pr code review: <base>` | The lens reviewers vs a custom base |

For the underlying deterministic commands (no AI, no tokens), see
`.ai/skills/validate-code/SKILL.md`.

### `review pr`

Independent review of an open pull request without checking it out, for example one on another
branch.

- `review pr: <number>` — look up the base and head with `gh pr view <number> --json
  baseRefName,headRefName`, run `git fetch origin`, then
  `python -m scripts.checks.repo.review_scope_check --base origin/<base> --head origin/<head>` for
  the reviewers, and follow "For the orchestrator" in `.ai/skills/code-review/lenses.md` with those
  refs. Print the verified findings; do not fix them.
- The standing authorization covers only the readiness comment on the current branch's own PR, so
  posting these findings to another PR needs the owner's yes.

### `implement plan`

Implement one plan from `plan/` on its own branch and open a pull request. Follow
`.ai/skills/implement-plan/SKILL.md`.

- `implement plan: <file>` — plan `plan/<file>`, in this session
- `python -m scripts.forge implement-plan --plan plan/<file>` — the unattended pickup: claims the plan
  with a draft pull request, runs the agent, runs the gate, and takes the pull request out of draft only
  when the gate passes, no guarded path was touched, and the agent raised no question. Commits that touch
  a guarded path are never pushed or applied: they are kept in a local-only ref (`refs/forge/held/<branch>/<commit>`)
  for the owner to inspect, because GitHub runs workflow files from a pushed commit. When the pull
  request does leave draft, the command waits for the first review and runs the fixer loop (`fix-loop`) on that pull request, unless `--no-fix` is given
- `--container` runs the pickup's gate in a Docker container instead of on the owner's machine: no network, a
  read-only root, no capabilities, five environment variables and no host secrets, and only the clean clone
  mounted. The image is built from the owner's checkout (`docker/gate/Dockerfile`, a guarded path), so the
  agent cannot change it. It does not isolate the agent, which still runs as described under Standing
  authorizations, and it does not run the frontend checks (CI does).
- Invoking either is what authorizes the new branch, the pushes to it, the draft pull request, that one
  transition out of draft, and the fixer loop that follows within its own standing authorization. A start
  from a schedule or a trigger needs its own standing authorization.

### `fix pr`

Resolve the open findings in a pull request's readiness comment. Follow
`.ai/skills/fix-pr-readiness/SKILL.md`.

- `fix pr` — the current branch's pull request
- `fix pr: <number>` — pull request `<number>`
- Invoking it is what authorizes the commits, the push to the pull request branch, and the comment edit
  the skill describes. An unattended run needs its own standing authorization above.
